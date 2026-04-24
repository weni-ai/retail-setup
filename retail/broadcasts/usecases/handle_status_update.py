import logging

from dataclasses import dataclass
from typing import Any, Dict, Optional

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.broadcasts.models import (
    BroadcastMessage,
    BroadcastStatus,
    ProjectBroadcastCounter,
)
from retail.broadcasts.usecases.project_limit_guard import ProjectLimitGuard

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BroadcastStatusEvent:
    """Normalized representation of a msgs.topic event."""

    message_id: Optional[str]
    broadcast_id: Optional[int]
    status: Optional[str]
    payload: Dict[str, Any]


class HandleStatusUpdateUseCase:
    """Applies a status event coming from the courier to a BroadcastMessage.

    Handles two distinct flows:
      - Create event: carries both broadcast_id and message_id; links the
        external_message_id (Meta's ID) to the row created at dispatch.
      - Status-only event: carries only message_id; updates the row status.

    The DELIVERED transition is idempotent and triggers an atomic increment
    on ProjectBroadcastCounter.total_delivered (outbound broadcast counter,
    not the conversation counter), checking the broadcast limit afterwards
    through ProjectLimitGuard.
    """

    def __init__(self, limit_guard: Optional[ProjectLimitGuard] = None):
        self.limit_guard = limit_guard or ProjectLimitGuard()

    def execute(self, event: BroadcastStatusEvent) -> None:
        # msgs.topic is a shared exchange; most events will not match any
        # broadcast we recorded. Unknown ids are silently discarded to keep
        # log volume manageable — only matching rows produce log entries.
        if event.broadcast_id is not None and event.message_id:
            self._link_message_to_broadcast(event)
            return

        if event.message_id:
            self._update_status_by_message_id(event)
            return

    def _link_message_to_broadcast(self, event: BroadcastStatusEvent) -> None:
        """Attach the Meta message_id to our dispatch row.

        select_for_update acquires a row lock at the SELECT so that a
        concurrent status-only event for the same message cannot race
        ahead and transition the status before the linkage is committed.
        The actual DB write happens on .save() inside the atomic block;
        the lock is released on commit.
        """
        broadcast_id = event.broadcast_id

        with transaction.atomic():
            message = (
                BroadcastMessage.objects.select_for_update()
                .filter(broadcast_id=broadcast_id)
                .first()
            )

            if message is None:
                return

            if (
                message.external_message_id
                and message.external_message_id != event.message_id
            ):
                # Rare anomaly: same broadcast_id paired with a different
                # message_id than what we already stored. Indicates an
                # unexpected re-send or courier bug.
                logger.warning(
                    f"Conflicting external_message_id for broadcast_id={broadcast_id}: "
                    f"existing={message.external_message_id} "
                    f"incoming={event.message_id} "
                    f"status={event.status}"
                )

            message.external_message_id = event.message_id
            message.last_payload = event.payload
            message.save(
                update_fields=["external_message_id", "last_payload", "updated_at"]
            )

            logger.info(
                "WhatsApp message from Meta API linked to broadcast. "
                f"broadcast_id={broadcast_id} "
                f"message_id={event.message_id} "
                f"status={event.status} "
                f"broadcast_uuid={message.uuid}"
            )

            if event.status:
                self._apply_status_transition(message, event)

    def _update_status_by_message_id(self, event: BroadcastStatusEvent) -> None:
        """Status-only events look up the row by message_id (Meta's ID).

        The courier drops broadcast_id after the first create event so
        all subsequent updates arrive with only message_id.

        select_for_update acquires the lock at the SELECT. The DB write
        happens in _apply_status_transition via .save(), still inside the
        same atomic block, before the lock is released on commit.
        """
        message_id = event.message_id

        with transaction.atomic():
            message = (
                BroadcastMessage.objects.select_for_update()
                .filter(external_message_id=message_id)
                .first()
            )

            if message is None:
                return

            logger.info(
                "Status event received for tracked broadcast. "
                f"message_id={message_id} "
                f"status={event.status} "
                f"broadcast_uuid={message.uuid}"
            )

            self._apply_status_transition(message, event)

    def _apply_status_transition(
        self, message: BroadcastMessage, event: BroadcastStatusEvent
    ) -> None:
        """Persist the new status and handle side-effects on DELIVERED.

        Accepts the already-locked BroadcastMessage object to avoid a
        redundant SELECT inside the caller's transaction.

        Unknown statuses are saved as UNKNOWN (not dropped) so their
        payloads can be analyzed and the enum extended later if needed.
        """
        new_status = (event.status or "").lower() or None
        if new_status is None:
            return

        valid_values = {choice for choice, _ in BroadcastStatus.choices}
        if new_status not in valid_values:
            logger.warning(
                f"Unrecognized status '{new_status}' from courier; "
                f"saving as UNKNOWN. broadcast_uuid={message.uuid}"
            )
            new_status = BroadcastStatus.UNKNOWN

        previous_status = message.status
        message.previous_status = previous_status
        message.status = new_status
        message.status_updated_at = timezone.now()
        message.last_payload = event.payload
        message.save(
            update_fields=[
                "previous_status",
                "status",
                "status_updated_at",
                "last_payload",
                "updated_at",
            ]
        )

        logger.info(
            f"Status transition: {previous_status} → {new_status}. "
            f"broadcast_uuid={message.uuid}"
        )

        is_first_delivery = (
            new_status == BroadcastStatus.DELIVERED
            and previous_status != BroadcastStatus.DELIVERED
        )
        if is_first_delivery:
            self._increment_broadcast_counter_and_maybe_block(
                project_id=message.project_id,
                integrated_agent_id=message.integrated_agent_id,
            )

    def _increment_broadcast_counter_and_maybe_block(
        self,
        project_id: int,
        integrated_agent_id: Optional[str],
    ) -> None:
        """Increment the delivered counters and re-evaluate the block guard.

        Two counters are incremented atomically:
          - ProjectBroadcastCounter.total_delivered — drives the blocking flow.
          - IntegratedAgent.broadcasts_delivered — per-agent analytics.

        Atomicity is required because multiple status events for the
        same project can be processed concurrently and a non-atomic
        increment would lose updates.
        """
        counter, _ = ProjectBroadcastCounter.objects.select_related(
            "project"
        ).get_or_create(project_id=project_id)
        ProjectBroadcastCounter.objects.filter(project_id=project_id).update(
            total_delivered=F("total_delivered") + 1,
            updated_at=timezone.now(),
        )

        if integrated_agent_id is not None:
            IntegratedAgent.objects.filter(uuid=integrated_agent_id).update(
                broadcasts_delivered=F("broadcasts_delivered") + 1,
            )

        counter.refresh_from_db(fields=["total_delivered", "blocked_at"])

        if self.limit_guard.should_block(counter):
            self.limit_guard.trigger_block(project_id)
