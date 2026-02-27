import logging

from django.conf import settings

from retail.clients.integrations.client import IntegrationsClient
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface
from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.onboarding_defaults import get_wwc_translations
from retail.services.integrations.service import IntegrationsService

logger = logging.getLogger(__name__)

# TODO: Review these configs with the product team before production.
WWC_CREATION_CONFIG = {
    "version": "2",
    "useConnectionOptimization": True,
}

WWC_CHANNEL_BASE_CONFIG = {
    "version": "2",
    "selector": "#wwc",
    "embedded": False,
    "mainColor": "#3d3d3d",
    "contactTimeout": 0,
    "startFullScreen": False,
    "showCameraButton": False,
    "showFullScreenButton": False,
    "showVoiceRecordingButton": False,
    "displayUnreadCount": True,
    "timeBetweenMessages": 1,
    "navigateIfSameDomain": False,
    "useConnectionOptimization": False,
    "displayRatio": 10,
    "params": {
        "images": {"dims": {"width": 300, "height": 200}},
        "storage": "local",
    },
    "customizeWidget": {
        "launcherColor": "#3d3d3d",
        "headerBackgroundColor": "#3d3d3d",
        "quickRepliesFontColor": "#3d3d3d",
        "userMessageBubbleColor": "#3d3d3d",
        "quickRepliesBorderColor": "#3d3d3d",
        "quickRepliesBackgroundColor": "#3d3d3d33",
    },
    "profileAvatar": settings.WWC_PROFILE_AVATAR_URL,
}


def build_wwc_channel_config(language: str) -> dict:
    """Builds the full WWC channel config with translated title and placeholder."""
    translations = get_wwc_translations(language)
    return {
        **WWC_CHANNEL_BASE_CONFIG,
        "title": translations["title"],
        "inputTextFieldHint": translations["inputTextFieldHint"],
    }


class WWCConfigError(Exception):
    """Raised when the WWC channel creation or configuration fails."""


class ConfigureWWCUseCase:
    """
    Creates and configures a WWC (Weni Web Chat) channel for a project.

    Flow:
        1. POST to create the WWC app → receives the app UUID.
        2. PATCH to configure the WWC app → channel is live.
        3. Stores the app UUID in onboarding.config.channels.wwc.
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

        Progress within NEXUS_CONFIG (runs first, before Nexus upload):
            3%  — WWC app created.
            7%  — WWC app configured.
            10% — App UUID persisted, WWC complete.

        Args:
            vtex_account: The VTEX account identifier for the onboarding.

        Raises:
            WWCConfigError: If any step fails or if a WWC channel
                is already configured for this onboarding.
        """
        onboarding = self._load_onboarding(vtex_account)
        project_uuid = str(onboarding.project.uuid)
        language = onboarding.project.language or ""

        onboarding.current_step = "NEXUS_CONFIG"
        onboarding.progress = 0
        onboarding.save(update_fields=["current_step", "progress"])

        app_uuid = self._create_app(onboarding, project_uuid)
        self._configure_app(onboarding, app_uuid, project_uuid, language)
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

        existing_wwc = (onboarding.config or {}).get("channels", {}).get("wwc", {})
        if existing_wwc.get("app_uuid"):
            raise WWCConfigError(
                f"WWC channel already configured for onboarding={onboarding.uuid} "
                f"(app_uuid={existing_wwc['app_uuid']}). Aborting to avoid duplicate."
            )

        return onboarding

    def _create_app(self, onboarding: ProjectOnboarding, project_uuid: str) -> str:
        """Creates the WWC app and updates progress to 10%."""
        create_response = self.integrations_service.create_channel_app(
            "wwc", project_uuid, WWC_CREATION_CONFIG
        )
        if create_response is None:
            raise WWCConfigError(f"Failed to create WWC app for project={project_uuid}")

        app_uuid = create_response.get("uuid")
        if not app_uuid:
            raise WWCConfigError(
                f"WWC app creation returned no uuid for project={project_uuid}"
            )

        onboarding.progress = 3
        onboarding.save(update_fields=["progress"])
        logger.info(f"WWC app created: app_uuid={app_uuid} project={project_uuid}")

        return app_uuid

    def _configure_app(
        self,
        onboarding: ProjectOnboarding,
        app_uuid: str,
        project_uuid: str,
        language: str = "",
    ) -> None:
        """Configures the previously created WWC app and updates progress to 20%."""
        channel_config = build_wwc_channel_config(language)
        configure_response = self.integrations_service.configure_channel_app(
            "wwc", app_uuid, channel_config
        )
        if configure_response is None:
            raise WWCConfigError(
                f"Failed to configure WWC app={app_uuid} for project={project_uuid}"
            )

        onboarding.progress = 7
        onboarding.save(update_fields=["progress"])
        logger.info(f"WWC app configured: app_uuid={app_uuid} project={project_uuid}")

    @staticmethod
    def _persist_app_uuid(onboarding: ProjectOnboarding, app_uuid: str) -> None:
        """Stores the app UUID in config and marks progress as 10%."""
        config = onboarding.config or {}
        channels = config.setdefault("channels", {})
        channels["wwc"] = {**channels.get("wwc", {}), "app_uuid": app_uuid}
        onboarding.config = config
        onboarding.progress = 10
        onboarding.save(update_fields=["config", "progress"])

        logger.info(
            f"WWC channel stored in onboarding config: "
            f"vtex_account={onboarding.vtex_account} app_uuid={app_uuid}"
        )
