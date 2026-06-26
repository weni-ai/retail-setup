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


# Position of each status in the forward lifecycle. Used to reject
# out-of-order events (e.g. a "sent" arriving after "delivered" because
# the courier reordered the message). Statuses absent from this map
# (terminals and UNKNOWN) are handled separately and always accepted.
_STATUS_RANK = {
    BroadcastStatus.INITIALIZING: 10,
    BroadcastStatus.PENDING: 20,
    BroadcastStatus.QUEUED: 30,
    BroadcastStatus.SENT: 40,
    BroadcastStatus.WIRED: 50,
    BroadcastStatus.DELIVERED: 60,
    BroadcastStatus.READ: 70,
}

# Statuses that may legitimately arrive at any point in the lifecycle
# (e.g. a delivery failure can be reported even after a previous
# success notification due to provider-side issues).
_ALWAYS_ACCEPTED = frozenset(
    {BroadcastStatus.ERRORED, BroadcastStatus.FAILED, BroadcastStatus.UNKNOWN}
)


@dataclass(frozen=True)
class BroadcastStatusEvent:
    """Normalized representation of a msgs.topic event.

    ``status`` is already mapped to a ``BroadcastStatus`` value by the
    consumer (``CourierStatusMapper``) before reaching the use case;
    a value of ``None`` means the event carried no status to apply.
    """

    message_id: Optional[str]
    broadcast_id: Optional[int]
    status: Optional[str]
    payload: Dict[str, Any]


class HandleStatusUpdateUseCase:
    """Applies a status event coming from the courier to a BroadcastMessage.

    Two routing-key-driven flows are exposed as public methods:
      - ``link_send_event``: handles the first event of a new outbound
        broadcast (template-send). Links the external_message_id
        (Meta's ID) to the row created at dispatch.
      - ``apply_status_event``: handles subsequent transitions
        (template-status). Updates the row status by message_id.

    The DELIVERED transition is idempotent and triggers an atomic increment
    on ProjectBroadcastCounter.total_delivered (outbound broadcast counter,
    not the conversation counter), checking the broadcast limit afterwards
    through ProjectLimitGuard.
    """

    def __init__(self, limit_guard: Optional[ProjectLimitGuard] = None):
        self.limit_guard = limit_guard or ProjectLimitGuard()

    def link_send_event(self, event: BroadcastStatusEvent) -> None:
        """Public entry point for the template-send routing key.

        Events without a ``broadcast_id`` are non-broadcast templates
        (NPS, pickup notifications, etc.) flowing through the same
        courier topic. They are discarded silently since there is no
        BroadcastMessage row to link.
        """
        if event.broadcast_id is None:
            logger.debug(
                f"[BROADCAST_TRACKING] send_event_missing_broadcast_id: "
                f"message_id={event.message_id} payload={event.payload}"
            )
            return
        if not event.message_id:
            logger.error(
                f"[BROADCAST_TRACKING] send_event_missing_message_id: "
                f"broadcast_id={event.broadcast_id} payload={event.payload}"
            )
            return
        self._link_message_to_broadcast(event)

    def apply_status_event(self, event: BroadcastStatusEvent) -> None:
        """Public entry point for the template-status routing key.

        Status events are looked up by ``message_id`` only; any
        ``broadcast_id`` in the payload is ignored on purpose because
        the courier emits 0 (or omits it) at this stage.
        """
        if not event.message_id:
            return
        self._update_status_by_message_id(event)

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
                    f"[BROADCAST_TRACKING] message_id_conflict: "
                    f"broadcast_uuid={message.uuid} broadcast_id={broadcast_id} "
                    f"existing_message_id={message.external_message_id} "
                    f"incoming_message_id={event.message_id} status={event.status}"
                )

            message.external_message_id = event.message_id
            message.last_payload = event.payload
            message.save(
                update_fields=["external_message_id", "last_payload", "updated_at"]
            )

            logger.info(
                f"[BROADCAST_TRACKING] linked: "
                f"broadcast_uuid={message.uuid} broadcast_id={broadcast_id} "
                f"message_id={event.message_id} status={event.status}"
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
                f"[BROADCAST_TRACKING] status_received: "
                f"broadcast_uuid={message.uuid} message_id={message_id} "
                f"status={event.status}"
            )

            self._apply_status_transition(message, event)

    def _apply_status_transition(
        self, message: BroadcastMessage, event: BroadcastStatusEvent
    ) -> None:
        """Persist the new status and handle side-effects on DELIVERED.

        Accepts the already-locked BroadcastMessage object to avoid a
        redundant SELECT inside the caller's transaction.

        The ``event.status`` is expected to already be a mapped
        ``BroadcastStatus`` value (the consumer translates the courier's
        single-letter status before reaching here). UNKNOWN is preserved
        as-is so the payload can be diagnosed later.
        """
        new_status = event.status
        if new_status is None:
            return

        previous_status = message.status

        if self._is_out_of_order(previous_status, new_status):
            logger.info(
                f"[BROADCAST_TRACKING] status_out_of_order_ignored: "
                f"broadcast_uuid={message.uuid} "
                f"previous_status={previous_status} "
                f"incoming_status={new_status}"
            )
            return

        if new_status == BroadcastStatus.UNKNOWN:
            self._log_unknown_status_for_drill_down(message, event)

        message.previous_status = previous_status
        message.status = new_status
        message.status_updated_at = timezone.now()
        message.last_payload = event.payload

        update_fields = [
            "previous_status",
            "status",
            "status_updated_at",
            "last_payload",
            "updated_at",
        ]

        if new_status in (BroadcastStatus.ERRORED, BroadcastStatus.FAILED):
            message.error_message = self._extract_error_reason(event, new_status)
            update_fields.append("error_message")

        message.save(update_fields=update_fields)

        logger.info(
            f"[BROADCAST_TRACKING] status_transition: "
            f"broadcast_uuid={message.uuid} "
            f"previous_status={previous_status} new_status={new_status}"
        )

        is_first_delivery = (
            new_status == BroadcastStatus.DELIVERED
            and previous_status != BroadcastStatus.DELIVERED
        )
        if is_first_delivery:
            self._increment_broadcast_counter_and_maybe_block(
                project_id=message.project_id,
                integrated_agent_id=message.integrated_agent_id,
                broadcast_uuid=message.uuid,
            )

    @staticmethod
    def _extract_error_reason(
        event: BroadcastStatusEvent, status: BroadcastStatus
    ) -> str:
        """Pull a human-readable error from the courier payload so a row
        transitioning to ERRORED/FAILED never ends up with an empty
        error_message. Falls back to a synthetic reason when the courier
        carries no error/message field."""
        payload = event.payload or {}
        for key in ("error", "message", "detail"):
            value = payload.get(key)
            if value:
                return str(value)
        return f"Courier reported status={status} without error detail"

    @staticmethod
    def _is_out_of_order(previous_status: str, new_status: BroadcastStatus) -> bool:
        """Return True when the incoming status would regress the row
        backwards in the forward lifecycle.

        The courier may publish status updates out of order (network
        retries, provider reordering). Without this guard a "sent"
        arriving after a "delivered" would silently downgrade the row,
        and the next "delivered" would incorrectly be counted as a new
        first-delivery — duplicating the project counter.

        Terminal states (ERRORED, FAILED) and UNKNOWN are always
        accepted because they may legitimately follow any previous
        status (e.g. a late failure notification).
        """
        if new_status in _ALWAYS_ACCEPTED:
            return False
        if previous_status in _ALWAYS_ACCEPTED:
            # Once the row reached a terminal/unknown state we still
            # allow forward progress (e.g. a follow-up DELIVERED after
            # an UNKNOWN). Only block backwards moves below.
            pass

        new_rank = _STATUS_RANK.get(new_status)
        prev_rank = _STATUS_RANK.get(previous_status)
        if new_rank is None or prev_rank is None:
            return False
        return new_rank < prev_rank

    def _log_unknown_status_for_drill_down(
        self, message: BroadcastMessage, event: BroadcastStatusEvent
    ) -> None:
        """Emit a per-broadcast log line when an UNKNOWN status is persisted.

        ``CourierStatusMapper`` already logs the unmapped courier letter
        with no row context. This method complements that log by tying
        the same event to the specific ``broadcast_uuid``, enabling
        operators to drill down by message in dashboards instead of only
        seeing the aggregate "we got status X today".
        """
        logger.warning(
            f"[BROADCAST_TRACKING] status_unknown_persisted: "
            f"broadcast_uuid={message.uuid} "
            f"raw_payload_status={event.payload.get('status')!r}"
        )

    def _increment_broadcast_counter_and_maybe_block(
        self,
        project_id: int,
        integrated_agent_id: Optional[int],
        broadcast_uuid,
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

        agent_total: Optional[int] = None
        if integrated_agent_id is not None:
            IntegratedAgent.objects.filter(pk=integrated_agent_id).update(
                broadcasts_delivered=F("broadcasts_delivered") + 1,
            )
            agent_total = (
                IntegratedAgent.objects.filter(pk=integrated_agent_id)
                .values_list("broadcasts_delivered", flat=True)
                .first()
            )

        counter.refresh_from_db(fields=["total_delivered", "blocked_at"])

        logger.info(
            f"[BROADCAST_TRACKING] counters_incremented: "
            f"broadcast_uuid={broadcast_uuid} "
            f"project_uuid={counter.project.uuid} "
            f"project_total_delivered={counter.total_delivered} "
            f"agent_id={integrated_agent_id} "
            f"agent_total_delivered={agent_total}"
        )

        if self.limit_guard.should_block(counter):
            self.limit_guard.trigger_block(project_id)
