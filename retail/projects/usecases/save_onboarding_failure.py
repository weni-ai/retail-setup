import logging
from typing import Any, Mapping, Optional

from django.utils import timezone

from retail.projects.usecases.onboarding_access import get_or_create_active_onboarding

logger = logging.getLogger(__name__)


class SaveOnboardingFailureUseCase:
    """
    Stores a snapshot of a failed onboarding attempt in ProjectOnboarding.config.

    Used to debug and recover cases where the onboarding could not proceed
    (e.g., invalid payload from the front-end, external service failures).

    The payload is stored under config["last_failure"] and is overwritten
    on each new failure. It is cleared when a new attempt is made via
    StartSetupUseCase (see _reset_onboarding).

    Fail-safe: exceptions are logged and never propagated, so the caller's
    flow is not affected by persistence issues.
    """

    @staticmethod
    def execute(
        vtex_account: str,
        stage: str,
        payload: Optional[Mapping[str, Any]] = None,
        errors: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """
        Args:
            vtex_account: VTEX account identifier.
            stage: Short code identifying where the failure happened
                (e.g., "start_setup_validation", "crawler_start").
            payload: The raw payload received by the backend.
            errors: The validation or processing errors (serializable).
        """
        try:
            onboarding, _ = get_or_create_active_onboarding(vtex_account=vtex_account)
            config = onboarding.config or {}
            config["last_failure"] = {
                "timestamp": timezone.now().isoformat(),
                "stage": stage,
                "errors": _to_plain(errors),
                "payload": _to_plain(payload),
            }
            onboarding.config = config
            onboarding.save(update_fields=["config"])

            logger.info(
                f"[SaveOnboardingFailure] stored failure "
                f"vtex_account={vtex_account} stage={stage}"
            )
        except Exception as exc:
            logger.error(
                f"[SaveOnboardingFailure] could not store failure for "
                f"vtex_account={vtex_account}: {exc}"
            )


def _to_plain(value: Any) -> Any:
    """
    Converts DRF ``ErrorDetail`` and ``ReturnDict`` structures into plain
    JSON-serializable types so they can be safely stored in a JSONField.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
