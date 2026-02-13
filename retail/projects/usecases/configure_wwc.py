import logging

from retail.clients.integrations.client import IntegrationsClient
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface
from retail.projects.models import ProjectOnboarding
from retail.services.integrations.service import IntegrationsService

logger = logging.getLogger(__name__)

# TODO: Review these configs with the product team before production.
WWC_CREATION_CONFIG = {
    "version": "2",
    "useConnectionOptimization": True,
}

# TODO: Review these configs with the product team before production.
WWC_CHANNEL_CONFIG = {
    "title": "Chat",
    "showFullScreenButton": False,
    "displayUnreadCount": False,
    "timeBetweenMessages": 1,
    "keepHistory": False,
    "startFullScreen": False,
    "showVoiceRecordingButton": False,
    "showCameraButton": False,
    "useConnectionOptimization": True,
    "navigateIfSameDomain": False,
    "embedded": False,
    "mainColor": "#009E96",
    "contactTimeout": 0,
    "version": "2",
}


class WWCConfigError(Exception):
    """Raised when the WWC channel creation or configuration fails."""


class ConfigureWWCUseCase:
    """
    Creates and configures a WWC (Weni Web Chat) channel for a project.

    Flow:
        1. POST to create the WWC app → receives the app UUID.
        2. PATCH to configure the WWC app → channel is live.
        3. Stores the app UUID in onboarding.config.integrated_apps.wwc.
    """

    def __init__(
        self,
        integrations_client: IntegrationsClientInterface = None,
    ):
        self.integrations_service = IntegrationsService(
            client=integrations_client or IntegrationsClient()
        )

    def execute(self, vtex_account: str) -> None:
        """
        Orchestrates WWC channel creation and configuration.

        Progress within NEXUS_CONFIG:
            85% — WWC app created.
            95% — WWC app configured.
            100% — App UUID persisted, step complete.

        Args:
            vtex_account: The VTEX account identifier for the onboarding.

        Raises:
            WWCConfigError: If any step fails or if a WWC channel
                is already configured for this onboarding.
        """
        onboarding = self._load_onboarding(vtex_account)
        project_uuid = str(onboarding.project.uuid)

        app_uuid = self._create_app(onboarding, project_uuid)
        self._configure_app(onboarding, app_uuid, project_uuid)
        self._persist_app_uuid(onboarding, app_uuid)

    def _load_onboarding(self, vtex_account: str) -> ProjectOnboarding:
        """Loads and validates the onboarding record."""
        onboarding = ProjectOnboarding.objects.select_related("project").get(
            vtex_account=vtex_account
        )

        if onboarding.project is None:
            raise WWCConfigError(
                f"Onboarding {onboarding.uuid} has no project linked yet."
            )

        existing_wwc = (onboarding.config or {}).get("integrated_apps", {}).get("wwc")
        if existing_wwc:
            raise WWCConfigError(
                f"WWC channel already configured for onboarding={onboarding.uuid} "
                f"(app_uuid={existing_wwc}). Aborting to avoid duplicate."
            )

        return onboarding

    def _create_app(self, onboarding: ProjectOnboarding, project_uuid: str) -> str:
        """Creates the WWC app and updates progress to 85%."""
        create_response = self.integrations_service.create_wwc_app(
            project_uuid, WWC_CREATION_CONFIG
        )
        if create_response is None:
            raise WWCConfigError(f"Failed to create WWC app for project={project_uuid}")

        app_uuid = create_response.get("uuid")
        if not app_uuid:
            raise WWCConfigError(
                f"WWC app creation returned no uuid for project={project_uuid}"
            )

        onboarding.progress = 85
        onboarding.save(update_fields=["progress"])
        logger.info(f"WWC app created: app_uuid={app_uuid} project={project_uuid}")

        return app_uuid

    def _configure_app(
        self, onboarding: ProjectOnboarding, app_uuid: str, project_uuid: str
    ) -> None:
        """Configures the previously created WWC app and updates progress to 95%."""
        configure_response = self.integrations_service.configure_wwc_app(
            app_uuid, WWC_CHANNEL_CONFIG
        )
        if configure_response is None:
            raise WWCConfigError(
                f"Failed to configure WWC app={app_uuid} for project={project_uuid}"
            )

        onboarding.progress = 95
        onboarding.save(update_fields=["progress"])
        logger.info(f"WWC app configured: app_uuid={app_uuid} project={project_uuid}")

    @staticmethod
    def _persist_app_uuid(onboarding: ProjectOnboarding, app_uuid: str) -> None:
        """Stores the app UUID in config and marks progress as 100%."""
        config = onboarding.config or {}
        integrated_apps = config.get("integrated_apps", {})
        integrated_apps["wwc"] = app_uuid
        config["integrated_apps"] = integrated_apps
        onboarding.config = config
        onboarding.progress = 100
        onboarding.save(update_fields=["config", "progress"])

        logger.info(
            f"WWC channel stored in onboarding config: "
            f"vtex_account={onboarding.vtex_account} app_uuid={app_uuid}"
        )
