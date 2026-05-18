import logging

from retail.clients.integrations.client import IntegrationsClient
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface
from retail.projects.models import ProjectOnboarding
from retail.services.integrations.service import IntegrationsService

logger = logging.getLogger(__name__)


# Progress markers within the PROJECT_CONFIG step.
# The pre-crawl pipeline sets PROJECT_CONFIG_START before invoking this
# use case; we drive it the rest of the way to 100% as the Meta handshake
# completes inside integrations-engine.
PROJECT_CONFIG_START = 50
PROJECT_CONFIG_AFTER_CREATE = 75
PROJECT_CONFIG_AFTER_PERSIST = 100


class WPPCloudConfigError(Exception):
    """Raised when the WPP Cloud channel creation fails."""


class ConfigureWPPCloudUseCase:
    """
    Creates a WhatsApp Cloud channel for a project via the integrations-engine.

    Runs as part of the pre-crawl pipeline (PROJECT_CONFIG step) so the
    short-lived Facebook ``auth_code`` is exchanged immediately, before
    the long-running crawl can expire it.

    The channel_data (auth_code, waba_id, phone_number_id) is read from
    onboarding.config.channels['wpp-cloud'].channel_data, where it was
    stored by StartSetupUseCase at the beginning of the flow.

    Flow:
        1. Read channel_data from the onboarding config.
        2. POST to integrations-engine to create the wpp-cloud app
           (engine handles the full Meta API setup internally).
        3. Store app_uuid and flow_object_uuid in onboarding config.

    The use case is idempotent at the "already-configured" level: if the
    app_uuid is already persisted, the call is logged and returns
    without raising. This lets the wrapping Celery task retry safely
    when an upstream step fails after channel creation already succeeded.
    """

    def __init__(
        self,
        integrations_client: IntegrationsClientInterface = None,
    ):
        self.integrations_service = IntegrationsService(
            client=integrations_client or IntegrationsClient()
        )

    def execute(self, vtex_account: str) -> None:
        onboarding = ProjectOnboarding.objects.select_related("project").get(
            vtex_account=vtex_account
        )

        if onboarding.project is None:
            raise WPPCloudConfigError(
                f"Onboarding {onboarding.uuid} has no project linked yet."
            )

        existing = (onboarding.config or {}).get("channels", {}).get("wpp-cloud", {})
        if existing.get("app_uuid"):
            logger.info(
                f"WPP Cloud channel already configured for onboarding={onboarding.uuid} "
                f"(app_uuid={existing['app_uuid']}). Skipping."
            )
            return

        project_uuid = str(onboarding.project.uuid)
        channel_data = self._get_channel_data(onboarding)

        onboarding.current_step = "PROJECT_CONFIG"
        onboarding.progress = PROJECT_CONFIG_START
        onboarding.save(update_fields=["current_step", "progress"])

        app_data = self._create_channel(onboarding, project_uuid, channel_data)
        self._persist_app_data(onboarding, app_data)

    @staticmethod
    def _get_channel_data(onboarding: ProjectOnboarding) -> dict:
        channels = (onboarding.config or {}).get("channels", {})
        channel_data = channels.get("wpp-cloud", {}).get("channel_data", {})

        if not channel_data:
            raise WPPCloudConfigError(
                f"No channel_data found in onboarding config for "
                f"vtex_account={onboarding.vtex_account}. "
                f"Ensure start-setup was called with channel_data."
            )

        required_fields = ["auth_code", "waba_id", "phone_number_id"]
        missing = [f for f in required_fields if not channel_data.get(f)]
        if missing:
            raise WPPCloudConfigError(
                f"Missing required fields in channel_data: {missing}"
            )

        return channel_data

    def _create_channel(
        self,
        onboarding: ProjectOnboarding,
        project_uuid: str,
        channel_data: dict,
    ) -> dict:
        response = self.integrations_service.create_wpp_cloud_channel(
            project_uuid=project_uuid,
            auth_code=channel_data["auth_code"],
            waba_id=channel_data["waba_id"],
            phone_number_id=channel_data["phone_number_id"],
        )

        if response is None:
            raise WPPCloudConfigError(
                f"Failed to create WPP Cloud channel for project={project_uuid}"
            )

        app_uuid = response.get("app_uuid")
        if not app_uuid:
            raise WPPCloudConfigError(
                f"WPP Cloud channel creation returned no app_uuid "
                f"for project={project_uuid}"
            )

        onboarding.progress = PROJECT_CONFIG_AFTER_CREATE
        onboarding.save(update_fields=["progress"])
        logger.info(
            f"WPP Cloud channel created: app_uuid={app_uuid} project={project_uuid}"
        )

        return response

    @staticmethod
    def _persist_app_data(onboarding: ProjectOnboarding, app_data: dict) -> None:
        app_uuid = app_data.get("app_uuid")
        flow_object_uuid = app_data.get("flow_object_uuid")

        config = onboarding.config or {}
        channels = config.setdefault("channels", {})
        wpp_cloud = channels.get("wpp-cloud", {})
        wpp_cloud["app_uuid"] = app_uuid
        wpp_cloud["flow_object_uuid"] = flow_object_uuid
        channels["wpp-cloud"] = wpp_cloud
        onboarding.config = config
        onboarding.progress = PROJECT_CONFIG_AFTER_PERSIST
        onboarding.save(update_fields=["config", "progress"])

        logger.info(
            f"WPP Cloud channel stored in onboarding config: "
            f"vtex_account={onboarding.vtex_account} "
            f"app_uuid={app_uuid} flow_object_uuid={flow_object_uuid}"
        )
