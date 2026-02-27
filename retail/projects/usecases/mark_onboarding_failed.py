import logging

from retail.projects.models import ProjectOnboarding

logger = logging.getLogger(__name__)


def mark_onboarding_failed(vtex_account: str, reason: str) -> None:
    """
    Sets failed=True and stores the reason in config["reason_failed"].

    Safe to call from any point in the onboarding flow. If the
    onboarding record doesn't exist or saving fails, the error
    is logged but never propagated.
    """
    try:
        onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
        onboarding.failed = True
        config = onboarding.config or {}
        config["reason_failed"] = reason
        onboarding.config = config
        onboarding.save(update_fields=["failed", "config"])

        logger.error(f"Onboarding failed for vtex_account={vtex_account}: {reason}")
    except Exception as exc:
        logger.error(
            f"Could not mark onboarding as failed for "
            f"vtex_account={vtex_account}: {exc}"
        )
