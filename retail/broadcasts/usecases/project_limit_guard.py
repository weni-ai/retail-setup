import logging

from typing import Optional

from django.db import transaction
from django.utils import timezone

from retail.broadcasts.models import ProjectBroadcastCounter
from retail.broadcasts.services.broadcast_limit_resolver import (
    BroadcastLimitResolver,
)
from retail.broadcasts.services.trial_suspension_service import (
    TrialSuspensionService,
)
from retail.projects.models import Project

logger = logging.getLogger(__name__)


class ProjectLimitGuard:
    """Enforces the per-project trial broadcast limit.

    A broadcast (PM term: "disparo") is an outbound message delivered to
    a contact on WhatsApp. This guard is not involved in the
    conversation-limit flow, which is owned by a separate consumer and
    tracks inbound user-initiated interactions.

    The applicable limit is resolved per project (Project.config override
    with global setting fallback). When the delivered counter crosses
    that limit, the guard marks the project as blocked locally
    (Project.is_blocked and ProjectBroadcastCounter.blocked_at) and
    delegates to TrialSuspensionService so the suspension also
    propagates to Connect.
    """

    def __init__(
        self,
        limit_resolver: Optional[BroadcastLimitResolver] = None,
        suspension_service: Optional[TrialSuspensionService] = None,
    ):
        self.limit_resolver = limit_resolver or BroadcastLimitResolver()
        self.suspension_service = suspension_service or TrialSuspensionService()

    def should_block(self, counter: ProjectBroadcastCounter) -> bool:
        """Return True when the counter has reached the project-specific
        limit (or global fallback) and the project is not yet blocked."""
        limit = self.limit_resolver.resolve(counter.project)
        if not limit:
            logger.debug(
                "Broadcast limit disabled; skipping block check. "
                f"project_id={counter.project_id}"
            )
            return False

        already_blocked = counter.blocked_at is not None
        reached_limit = counter.total_delivered >= limit

        logger.debug(
            "Block check: "
            f"project_id={counter.project_id} total_delivered={counter.total_delivered} "
            f"limit={limit} already_blocked={already_blocked}"
        )

        return not already_blocked and reached_limit

    def trigger_block(self, project_id: int) -> None:
        """Block the project locally and fire the external suspension flow.

        Idempotent: if the project is already blocked, returns silently.
        The external suspension call is isolated from the local update so
        that a failure in Connect does not leave the project in an
        inconsistent state locally.
        """
        now = timezone.now()

        with transaction.atomic():
            counter = (
                ProjectBroadcastCounter.objects.select_for_update()
                .select_related("project")
                .filter(project_id=project_id)
                .first()
            )
            if counter is None:
                logger.warning(
                    f"ProjectBroadcastCounter not found for project_id={project_id} "
                    f"while triggering block."
                )
                return

            if counter.blocked_at is not None:
                logger.info(
                    f"Project already blocked, skipping. project_id={project_id}"
                )
                return

            counter.blocked_at = now
            counter.save(update_fields=["blocked_at", "updated_at"])

            project = counter.project
            if not project.is_blocked:
                project.is_blocked = True
                project.save(update_fields=["is_blocked"])

            project_uuid = str(project.uuid)
            limit = self.limit_resolver.resolve(project) or 0

        self._invalidate_caches(project)

        logger.info(
            f"Project blocked locally due to trial broadcast limit. "
            f"project_uuid={project_uuid} broadcast_limit={limit} "
            f"total_delivered={counter.total_delivered}"
        )

        self.suspension_service.suspend(project_uuid=project_uuid, limit=limit)

    def _invalidate_caches(self, project: Project) -> None:
        try:
            project.clear_cache()
            project.clear_integrated_agents_cache()
        except Exception as exc:
            logger.warning(f"Failed to clear caches for project {project.uuid}: {exc}")
