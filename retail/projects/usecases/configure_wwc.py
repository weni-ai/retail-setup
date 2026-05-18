import logging

from retail.clients.integrations.client import IntegrationsClient
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface
from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.onboarding_defaults import get_wwc_translations
from retail.services.integrations.service import IntegrationsService

logger = logging.getLogger(__name__)

# TODO: Review these configs with the product team before production.
WWC_CREATION_CONFIG = {
    "version": "2",
    "useConnectionOptimization": False,
}

WWC_CHANNEL_BASE_CONFIG = {
    "version": "2",
    "selector": "#wwc",
    "embedded": False,
    "mainColor": "#0366DD",
    "contactTimeout": 0,
    "startFullScreen": False,
    "showCameraButton": False,
    "showFullScreenButton": True,
    "showVoiceRecordingButton": False,
    "displayUnreadCount": True,
    "addToCart": True,
    "timeBetweenMessages": 1,
    "navigateIfSameDomain": False,
    "conversationStartersPDP": True,
    "useConnectionOptimization": False,
    "renderPercentage": 10,
    "params": {
        "images": {"dims": {"width": 300, "height": 200}},
        "storage": "local",
    },
}


# Progress markers within the PROJECT_CONFIG step.
# Matched to the milestones in configure_wpp_cloud so the UI advances
# at a similar cadence regardless of which channel was selected.
PROJECT_CONFIG_START = 50
PROJECT_CONFIG_AFTER_CREATE = 66
PROJECT_CONFIG_AFTER_CONFIGURE = 83
PROJECT_CONFIG_AFTER_PERSIST = 100


def build_wwc_channel_config(language: str) -> dict:
    """Builds the full WWC channel config with translated title, subtitle and placeholder."""
    translations = get_wwc_translations(language)
    return {
        **WWC_CHANNEL_BASE_CONFIG,
        "title": translations["title"],
        "subtitle": translations["subtitle"],
        "inputTextFieldHint": translations["inputTextFieldHint"],
    }


class WWCConfigError(Exception):
    """Raised when the WWC channel creation or configuration fails."""


class ConfigureWWCUseCase:
    """
    Creates and configures a WWC (Weni Web Chat) channel for a project.

    Runs as part of the pre-crawl pipeline (PROJECT_CONFIG step) so the
    channel exists before the crawl starts, mirroring the WhatsApp
    Cloud flow.

    Flow:
        1. POST to create the WWC app → receives the app UUID.
        2. PATCH to configure the WWC app → channel is live.
        3. Stores the app UUID in onboarding.config.channels.wwc.

    The use case is idempotent at the "already-configured" level: if the
    app_uuid is already persisted, the call is logged and returns
    without raising.
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

        Progress within PROJECT_CONFIG (channel phase, before crawl):
            50% — Step started.
            66% — WWC app created.
            83% — WWC app configured.
            100% — App UUID persisted, channel ready for crawl handoff.

        Args:
            vtex_account: The VTEX account identifier for the onboarding.

        Raises:
            WWCConfigError: If any step fails.
        """
        onboarding = ProjectOnboarding.objects.select_related("project").get(
            vtex_account=vtex_account
        )

        if onboarding.project is None:
            raise WWCConfigError(
                f"Onboarding {onboarding.uuid} has no project linked yet."
            )

        existing_wwc = (onboarding.config or {}).get("channels", {}).get("wwc", {})
        if existing_wwc.get("app_uuid"):
            logger.info(
                f"WWC channel already configured for onboarding={onboarding.uuid} "
                f"(app_uuid={existing_wwc['app_uuid']}). Skipping."
            )
            return

        project_uuid = str(onboarding.project.uuid)
        language = onboarding.project.language or ""

        if not language:
            logger.warning(
                f"Project language is empty for project={project_uuid} "
                f"vtex_account={vtex_account}. WWC will use English defaults."
            )

        onboarding.current_step = "PROJECT_CONFIG"
        onboarding.progress = PROJECT_CONFIG_START
        onboarding.save(update_fields=["current_step", "progress"])

        app_uuid = self._create_app(onboarding, project_uuid)
        self._configure_app(onboarding, app_uuid, project_uuid, language)
        self._persist_app_uuid(onboarding, app_uuid)

    def _create_app(self, onboarding: ProjectOnboarding, project_uuid: str) -> str:
        """Creates the WWC app and advances PROJECT_CONFIG progress."""
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

        onboarding.progress = PROJECT_CONFIG_AFTER_CREATE
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
        """Configures the previously created WWC app and advances progress."""
        channel_config = build_wwc_channel_config(language)
        configure_response = self.integrations_service.configure_channel_app(
            "wwc", app_uuid, channel_config
        )
        if configure_response is None:
            raise WWCConfigError(
                f"Failed to configure WWC app={app_uuid} for project={project_uuid}"
            )

        onboarding.progress = PROJECT_CONFIG_AFTER_CONFIGURE
        onboarding.save(update_fields=["progress"])
        logger.info(f"WWC app configured: app_uuid={app_uuid} project={project_uuid}")

    @staticmethod
    def _persist_app_uuid(onboarding: ProjectOnboarding, app_uuid: str) -> None:
        """Stores the app UUID in config and completes the PROJECT_CONFIG step."""
        config = onboarding.config or {}
        channels = config.setdefault("channels", {})
        channels["wwc"] = {**channels.get("wwc", {}), "app_uuid": app_uuid}
        onboarding.config = config
        onboarding.progress = PROJECT_CONFIG_AFTER_PERSIST
        onboarding.save(update_fields=["config", "progress"])

        logger.info(
            f"WWC channel stored in onboarding config: "
            f"vtex_account={onboarding.vtex_account} app_uuid={app_uuid}"
        )
