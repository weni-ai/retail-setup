import logging
from typing import Optional

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.onboarding_dto import RequestOnboardingSupportDTO
from retail.services.notification.onboarding_support_service import (
    OnboardingSupportNotificationService,
)

logger = logging.getLogger(__name__)


class RequestOnboardingSupportUseCase:
    """
    Handles a "Contact support" request triggered by the front-end.

    Builds a full snapshot of the current onboarding state (status flags,
    progress, crawler result, linked project, config — including channels,
    last_failure and reason_failed) and forwards it together with the
    generic data sent by the front-end to the Slack notification service.

    The endpoint must always return success to the user — Slack outages
    or missing onboarding records must not block the support request.
    """

    def __init__(
        self,
        notification_service: Optional[OnboardingSupportNotificationService] = None,
    ):
        self.notification_service = (
            notification_service or OnboardingSupportNotificationService()
        )

    def execute(self, dto: RequestOnboardingSupportDTO) -> None:
        onboarding = self._fetch_onboarding(dto.vtex_account)
        current_step = onboarding.current_step if onboarding else None

        logger.info(
            f"Support requested for vtex_account={dto.vtex_account} "
            f"current_step={current_step or 'N/A'}"
        )

        self.notification_service.notify(
            vtex_account=dto.vtex_account,
            data=dto.data,
            onboarding=self._build_snapshot(onboarding),
        )

    @staticmethod
    def _fetch_onboarding(vtex_account: str) -> Optional[ProjectOnboarding]:
        try:
            return ProjectOnboarding.objects.select_related("project").get(
                vtex_account=vtex_account
            )
        except ProjectOnboarding.DoesNotExist:
            logger.warning(
                f"Support requested for vtex_account={vtex_account} "
                f"but no onboarding record was found."
            )
            return None

    @staticmethod
    def _build_snapshot(
        onboarding: Optional[ProjectOnboarding],
    ) -> Optional[dict]:
        if onboarding is None:
            return None

        project = onboarding.project
        return {
            "uuid": str(onboarding.uuid),
            "project_name": project.name if project else None,
            "project_uuid": str(project.uuid) if project else None,
            "current_step": onboarding.current_step or None,
            "current_page": onboarding.current_page or None,
            "progress": onboarding.progress,
            "completed": onboarding.completed,
            "failed": onboarding.failed,
            "skipped": onboarding.skipped,
            "crawler_result": onboarding.crawler_result,
            "created_on": (
                onboarding.created_on.isoformat() if onboarding.created_on else None
            ),
            "config": onboarding.config or {},
        }
