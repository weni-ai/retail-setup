import logging

from retail.clients.integrations.client import IntegrationsClient
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface
from retail.projects.models import ProjectOnboarding
from retail.services.integrations.service import IntegrationsService

logger = logging.getLogger(__name__)


class WPPCloudConfigError(Exception):
    """Raised when the WPP Cloud channel creation fails."""


class ConfigureWPPCloudUseCase:
    """
    Creates a WhatsApp Cloud channel for a project via the integrations-engine.

    The channel_data (auth_code, waba_id, phone_number_id) is read from
    onboarding.config.channels['wpp-cloud'].channel_data, where it was
    stored by StartSetupUseCase at the beginning of the flow.

    Flow:
        1. Read channel_data from the onboarding config.
        2. POST to integrations-engine to create the wpp-cloud app
           (engine handles the full Meta API setup internally).
        3. Store app_uuid and flow_object_uuid in onboarding config.
    """

    def __init__(
        self,
        integrations_client: IntegrationsClientInterface = None,
    ):
        self.integrations_service = IntegrationsService(
            client=integrations_client or IntegrationsClient()
        )

    def execute(self, vtex_account: str) -> None:
        onboarding = self._load_onboarding(vtex_account)
        project_uuid = str(onboarding.project.uuid)
        channel_data = self._get_channel_data(onboarding)

        onboarding.current_step = "NEXUS_CONFIG"
        onboarding.progress = 0
        onboarding.save(update_fields=["current_step", "progress"])

        app_data = self._create_channel(onboarding, project_uuid, channel_data)
        self._persist_app_data(onboarding, app_data)

    def _load_onboarding(self, vtex_account: str) -> ProjectOnboarding:
        onboarding = ProjectOnboarding.objects.select_related("project").get(
            vtex_account=vtex_account
        )

        if onboarding.project is None:
            raise WPPCloudConfigError(
                f"Onboarding {onboarding.uuid} has no project linked yet."
            )

        existing = (onboarding.config or {}).get("channels", {}).get("wpp-cloud", {})
        if existing.get("app_uuid"):
            raise WPPCloudConfigError(
                f"WPP Cloud channel already configured for onboarding={onboarding.uuid} "
                f"(app_uuid={existing['app_uuid']}). Aborting to avoid duplicate."
            )

        return onboarding

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

        onboarding.progress = 3
        onboarding.save(update_fields=["progress"])

        logger.info(
            f"WPP Cloud channel created: app_uuid={app_uuid} " f"project={project_uuid}"
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
        onboarding.progress = 10
        onboarding.save(update_fields=["config", "progress"])

        logger.info(
            f"WPP Cloud channel stored in onboarding config: "
            f"vtex_account={onboarding.vtex_account} "
            f"app_uuid={app_uuid} flow_object_uuid={flow_object_uuid}"
        )
