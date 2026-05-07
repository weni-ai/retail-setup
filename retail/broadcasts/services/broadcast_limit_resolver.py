import logging

from typing import Optional

from django.conf import settings

from retail.broadcasts.services.trial_status_service import TrialStatusService
from retail.projects.models import Project

logger = logging.getLogger(__name__)


class BroadcastLimitResolver:
    """Resolves the trial broadcast cap to apply on a project.

    The cap exists to gate trial accounts only. Paid plans must run
    without any local broadcast cap, so the resolver returns ``None``
    for them. The trial check is delegated to ``TrialStatusService``,
    which talks to Connect's plan-status endpoint (cached at both
    sides). When Connect is degraded the trial check fails open
    (treats the project as non-trial), so non-trial projects are never
    blocked by a transient billing lookup outage.

    Lookup order (for trial projects):
      1. Per-project override at ``Project.config[CONFIG_KEY]``, when set
         to a positive integer. This key is operational/billing control
         and is set manually via Django shell; it is not published by any
         known external EDA producer.
      2. Global fallback at ``settings.RETAIL_TRIAL_BROADCAST_LIMIT``.

    Returns ``None`` when no usable limit applies, in which case the
    blocking guard treats the cap as disabled.
    """

    CONFIG_KEY = "trial_broadcast_limit"

    def __init__(self, trial_status_service: Optional[TrialStatusService] = None):
        self.trial_status_service = trial_status_service or TrialStatusService()

    def resolve(self, project: Project) -> Optional[int]:
        if not self._is_trial(project):
            logger.debug(
                "Project is not in active trial; broadcast limit disabled. "
                f"project_uuid={project.uuid}"
            )
            return None

        override = self._project_override(project)
        if override is not None:
            return override
        return self._default_limit()

    def _is_trial(self, project: Project) -> bool:
        return self.trial_status_service.is_trial_active(project_uuid=str(project.uuid))

    def _project_override(self, project: Project) -> Optional[int]:
        raw = (project.config or {}).get(self.CONFIG_KEY)
        if raw is None:
            return None

        try:
            value = int(raw)
        except (TypeError, ValueError):
            logger.warning(
                f"Invalid {self.CONFIG_KEY!r} on project {project.uuid}: {raw!r}; "
                f"falling back to global default."
            )
            return None

        if value <= 0:
            return None
        return value

    @staticmethod
    def _default_limit() -> Optional[int]:
        limit = getattr(settings, "RETAIL_TRIAL_BROADCAST_LIMIT", None)
        if limit and limit > 0:
            return limit
        return None
