import logging

from django.utils import timezone

from retail.projects.models import ProjectOnboarding

logger = logging.getLogger(__name__)


class SaveBackgroundFailureUseCase:
    """
    Stores a snapshot of a background-phase failure (crawl + Nexus
    content upload) in ProjectOnboarding.config.

    Writes the snapshot under config["background_error"] WITHOUT
    flipping onboarding.failed -- the main onboarding may already be
    completed from the user's perspective by the time the background
    phase fails, and we don't want to retroactively flip a wizard that
    the user has already finished.

    The payload is overwritten on each new failure. It is cleared when
    a new attempt is made via StartSetupUseCase (see _reset_onboarding).

    Fail-safe: exceptions are logged and never propagated, so the
    caller's flow is not affected by persistence issues.
    """

    @staticmethod
    def execute(vtex_account: str, stage: str, error: str) -> None:
        """
        Args:
            vtex_account: VTEX account identifier.
            stage: Short code identifying where the failure happened
                (e.g. "crawler_start", "crawl", "nexus_upload").
            error: Human-readable error message.
        """
        try:
            onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
            config = onboarding.config or {}
            config["background_error"] = {
                "timestamp": timezone.now().isoformat(),
                "stage": stage,
                "error": error,
            }
            onboarding.config = config
            onboarding.save(update_fields=["config"])

            logger.info(
                f"[BackgroundFailure] recorded "
                f"vtex_account={vtex_account} stage={stage}"
            )
        except Exception as exc:
            logger.error(
                f"[BackgroundFailure] persist failed for "
                f"vtex_account={vtex_account}: {exc}"
            )
