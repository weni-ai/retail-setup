import logging

from typing import Optional

from django.core.cache import cache

from retail.clients.exceptions import CustomAPIException
from retail.interfaces.services.connect import ConnectServiceInterface
from retail.services.connect.service import ConnectService

logger = logging.getLogger(__name__)

# Local cache TTL on top of Connect's own 15-min server-side cache.
# Kept short and intentional: we only want to coalesce repeated lookups
# inside the same broadcast burst (status events arrive in clusters per
# project), not delay invalidation that already happens server-side on
# plan changes.
TRIAL_STATUS_CACHE_TTL_SECONDS = 30


class TrialStatusService:
    """Resolves whether a project is in an active trial.

    Source of truth is Connect's ``/v2/internals/connect/projects/{uuid}/
    plan-status`` endpoint, which already caches the answer for ~15
    minutes server-side and invalidates it via signals on plan changes.
    Only the ``is_trial_active`` field is consulted: it is pre-computed
    by Connect as ``plan == "trial" AND is_active AND NOT is_suspended``
    and is the documented single source of truth for trial-feature
    gating.

    A short local cache layer is added on top to avoid hitting the
    Connect HTTP service on every broadcast status event of the same
    project within the same minute. The TTL is intentionally smaller
    than Connect's so we still benefit from server-side invalidation
    triggered by plan changes.

    Failure mode: ``fail-open``. If Connect is unreachable or returns
    an unexpected payload, ``is_trial_active`` returns ``False`` so the
    trial broadcast cap is NOT applied. Rationale: a degraded billing
    lookup must not block paying customers; the worst case is that a
    trial project temporarily exceeds its cap, which can be reconciled
    later. The opposite (blocking paid customers) has direct revenue
    impact.
    """

    CACHE_KEY_TEMPLATE = "broadcasts:trial_status:{project_uuid}"

    def __init__(
        self,
        connect_service: Optional[ConnectServiceInterface] = None,
        cache_ttl_seconds: Optional[int] = None,
    ):
        self.connect_service = connect_service or ConnectService()
        self.cache_ttl_seconds = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else TRIAL_STATUS_CACHE_TTL_SECONDS
        )

    def is_trial_active(self, project_uuid: str) -> bool:
        """Return True only when the project is confirmed to be in trial."""
        cached_value = cache.get(self._cache_key(project_uuid))
        if cached_value is not None:
            return bool(cached_value)

        try:
            payload = self.connect_service.get_project_plan_status(
                project_uuid=project_uuid
            )
        except CustomAPIException as exc:
            # Fail-open: do not block the project on degraded lookups.
            logger.warning(
                "Could not resolve trial status from Connect; "
                f"assuming non-trial. project_uuid={project_uuid} "
                f"status_code={getattr(exc, 'status_code', None)} error={exc}"
            )
            return False

        is_trial_active = bool((payload or {}).get("is_trial_active", False))
        cache.set(
            self._cache_key(project_uuid),
            is_trial_active,
            timeout=self.cache_ttl_seconds,
        )
        return is_trial_active

    def _cache_key(self, project_uuid: str) -> str:
        return self.CACHE_KEY_TEMPLATE.format(project_uuid=project_uuid)
