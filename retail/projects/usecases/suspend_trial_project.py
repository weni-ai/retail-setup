import logging

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.suspend_trial_dto import SuspendTrialProjectDTO
from retail.services.connect.service import ConnectService
from retail.services.integrations.service import IntegrationsService
from retail.interfaces.clients.connect.interface import ConnectClientInterface
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface

logger = logging.getLogger(__name__)


class SuspendTrialError(Exception):
    """Raised when any step of the trial suspension flow fails."""


class SuspendTrialProjectUseCase:
    """
    Suspends a trial project that reached its conversation limit.

    Flow:
        1. Disables the WWC channel by setting renderPercentage to 0.
        2. Calls Connect to suspend the trial project (deactivates billing,
           suspends org, notifies Flows, sends email to admins).
    """

    def __init__(
        self,
        integrations_client: IntegrationsClientInterface = None,
        connect_client: ConnectClientInterface = None,
    ):
        self.integrations_service = IntegrationsService(client=integrations_client)
        self.connect_service = ConnectService(connect_client=connect_client)

    def execute(self, dto: SuspendTrialProjectDTO) -> None:
        logger.info(
            f"Starting trial suspension for project_uuid={dto.project_uuid} "
            f"conversation_limit={dto.conversation_limit}"
        )

        project = self._get_project(dto.project_uuid)
        wwc_app_uuid = self._get_wwc_app_uuid(project)

        if wwc_app_uuid:
            self._disable_wwc_channel(wwc_app_uuid, dto.project_uuid)
        else:
            logger.warning(
                f"No WWC channel found for project_uuid={dto.project_uuid}, "
                f"skipping renderPercentage update"
            )

        self._suspend_on_connect(dto.project_uuid, dto.conversation_limit)

        logger.info(f"Trial suspension completed for project_uuid={dto.project_uuid}")

    def _get_project(self, project_uuid: str) -> Project:
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise SuspendTrialError(f"Project not found: project_uuid={project_uuid}")

    def _get_wwc_app_uuid(self, project: Project) -> str | None:
        try:
            onboarding = project.onboarding
        except ProjectOnboarding.DoesNotExist:
            return None

        config = onboarding.config or {}
        wwc_channel = config.get("channels", {}).get("wwc", {})
        return wwc_channel.get("app_uuid")

    def _disable_wwc_channel(self, app_uuid: str, project_uuid: str) -> None:
        """Sets renderPercentage to 0 on the WWC channel, hiding the chat widget."""
        app_data = self.integrations_service.get_channel_app("wwc", app_uuid)
        if app_data is None:
            raise SuspendTrialError(
                f"Failed to retrieve WWC channel config: "
                f"app_uuid={app_uuid} project_uuid={project_uuid}"
            )

        config = app_data.get("config", {})
        config["renderPercentage"] = 0

        result = self.integrations_service.configure_channel_app(
            "wwc", app_uuid, config
        )
        if result is None:
            raise SuspendTrialError(
                f"Failed to disable WWC channel: "
                f"app_uuid={app_uuid} project_uuid={project_uuid}"
            )

        logger.info(
            f"WWC channel disabled (renderPercentage=0): "
            f"app_uuid={app_uuid} project_uuid={project_uuid}"
        )

    def _suspend_on_connect(self, project_uuid: str, conversation_limit: int) -> None:
        response = self.connect_service.suspend_trial_project(
            project_uuid=project_uuid,
            conversation_limit=conversation_limit,
        )
        logger.info(
            f"Project suspended on Connect: "
            f"project_uuid={project_uuid} response={response}"
        )
