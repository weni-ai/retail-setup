"""Configures the One-Click Payment integration for a WhatsApp number.

Runs as the final step of the WhatsApp Cloud onboarding flow. Wires
together three external systems so the merchant's phone number can
charge customers in a single tap:

  1. Generates an RSA 2048 key pair locally (the private key never
     leaves Weni).
  2. Sends the private key + channel identifiers to the payment
     microservice (creates/updates the channel record).
  3. Registers the matching public key with Meta on the phone number
     (used to encrypt the Flow payload server-side).
  4. Creates the encrypted Meta Flow whose ``endpoint_uri`` points back
     at the payment microservice webhook.
  5. Publishes the Meta Flow (a Flow is created in DRAFT and only
     becomes usable in messages after a publish call).

Retry semantics:
  When ``flow_id`` is already persisted but ``published`` is not,
  ``execute`` skips every external call up to (and including) the
  Flow creation and only retries the publish step. This keeps a
  failed publish from creating duplicate flows on Meta.
"""

import logging
from typing import Any, Dict, Optional

from django.conf import settings

from retail.clients.exceptions import CustomAPIException
from retail.clients.integrations.client import IntegrationsClient
from retail.clients.meta.client import MetaClient
from retail.clients.payment.client import PaymentClient
from retail.interfaces.clients.integrations.interface import (
    IntegrationsClientInterface,
)
from retail.interfaces.clients.meta.client import MetaClientInterface
from retail.interfaces.clients.payment.client import PaymentClientInterface
from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.one_click_payment_defaults import (
    PAYMENT_FLOW_CATEGORIES,
    build_payment_flow_json,
)
from retail.services.integrations.service import IntegrationsService
from retail.services.key_generator.service import (
    RSAKeyGeneratorService,
    RSAKeyPair,
)
from retail.services.meta.service import MetaService
from retail.services.payment.service import PaymentService

logger = logging.getLogger(__name__)


WPP_CLOUD_APPTYPE = "wpp-cloud"


class OneClickPaymentConfigError(Exception):
    """Raised when the One-Click Payment configuration step fails."""


class ConfigureOneClickPaymentUseCase:
    """Configures the One-Click Payment stack for the wpp-cloud channel."""

    def __init__(
        self,
        meta_client: Optional[MetaClientInterface] = None,
        payment_client: Optional[PaymentClientInterface] = None,
        integrations_client: Optional[IntegrationsClientInterface] = None,
        key_generator: Optional[RSAKeyGeneratorService] = None,
    ):
        self.meta_service = MetaService(client=meta_client or MetaClient())
        self.payment_service = PaymentService(client=payment_client or PaymentClient())
        self.integrations_service = IntegrationsService(
            client=integrations_client or IntegrationsClient()
        )
        self.key_generator = key_generator or RSAKeyGeneratorService()

    def execute(self, vtex_account: str) -> None:
        onboarding = self._load_onboarding(vtex_account)
        wpp_cloud = onboarding.config["channels"]["wpp-cloud"]
        channel_uuid = wpp_cloud["flow_object_uuid"]
        payment_state = wpp_cloud.get("payment") or {}

        flow_id = payment_state.get("flow_id")
        if flow_id is None:
            flow_id = self._provision(onboarding, wpp_cloud, channel_uuid)
        else:
            logger.info(
                f"Skipping provision step for vtex_account={vtex_account}: "
                f"flow_id={flow_id} already persisted, retrying publish only."
            )

        self._publish_flow(flow_id)
        self._mark_flow_published(onboarding)

        logger.info(
            f"One-Click Payment configured: "
            f"vtex_account={vtex_account} project={onboarding.project.uuid} "
            f"channel_uuid={channel_uuid} flow_id={flow_id}"
        )

    def _provision(
        self,
        onboarding: ProjectOnboarding,
        wpp_cloud: Dict[str, Any],
        channel_uuid: str,
    ) -> str:
        """Runs the create-side of the flow and persists ``flow_id``.

        Persisting the flow id immediately after Meta accepts the create
        call is what lets a later publish failure be retried without
        re-running this whole branch (which would create a second flow
        on Meta and leak orphan drafts).
        """
        project_uuid = str(onboarding.project.uuid)
        app_uuid = wpp_cloud["app_uuid"]

        endpoint_uri = self._build_payment_webhook_url(channel_uuid)
        channel_info = self._fetch_channel_info(app_uuid)

        keys = self.key_generator.generate()

        self._update_payment_channel(
            project_uuid=project_uuid,
            channel_uuid=channel_uuid,
            channel_info=channel_info,
            private_key_pem=keys.private_key_pem,
        )
        self._register_public_key(channel_info["phone_number_id"], keys)

        flow = self._create_meta_flow(
            waba_id=channel_info["waba_id"],
            channel_uuid=channel_uuid,
            endpoint_uri=endpoint_uri,
        )
        flow_id = flow["id"]

        self._persist_flow_created(onboarding, channel_uuid, flow_id)
        return flow_id

    def _load_onboarding(self, vtex_account: str) -> ProjectOnboarding:
        """Loads the onboarding and validates wpp-cloud channel readiness."""
        onboarding = ProjectOnboarding.objects.select_related("project").get(
            vtex_account=vtex_account
        )

        if onboarding.project is None:
            raise OneClickPaymentConfigError(
                f"Onboarding {onboarding.uuid} has no project linked yet."
            )

        wpp_cloud = (onboarding.config or {}).get("channels", {}).get("wpp-cloud")
        missing = [
            field
            for field in ("app_uuid", "flow_object_uuid")
            if not (wpp_cloud or {}).get(field)
        ]
        if missing:
            raise OneClickPaymentConfigError(
                f"WPP Cloud channel not configured for "
                f"vtex_account={vtex_account} (missing {missing}). "
                f"Cannot configure One-Click Payment."
            )

        if wpp_cloud.get("payment", {}).get("published"):
            raise OneClickPaymentConfigError(
                f"One-Click Payment already configured for "
                f"vtex_account={vtex_account}. Aborting to avoid duplicate."
            )

        return onboarding

    def _fetch_channel_info(self, app_uuid: str) -> Dict[str, str]:
        """Builds the metadata bundle expected by payment-ms / Meta.

        All fields come from integrations-engine, which is the canonical
        source after the wpp-cloud channel is provisioned.
        """
        app = self.integrations_service.get_channel_app(WPP_CLOUD_APPTYPE, app_uuid)
        if not app:
            raise OneClickPaymentConfigError(
                f"Failed to fetch wpp-cloud channel info from integrations "
                f"for app_uuid={app_uuid}"
            )

        config = app.get("config") or {}
        phone_number_block = config.get("phone_number") or {}
        info = {
            "phone_number": phone_number_block.get("display_phone_number"),
            "phone_number_id": phone_number_block.get("id"),
            "waba_id": (config.get("waba") or {}).get("id"),
        }

        missing = [field for field, value in info.items() if not value]
        if missing:
            raise OneClickPaymentConfigError(
                f"Missing wpp-cloud channel fields {missing} "
                f"for app_uuid={app_uuid}"
            )

        return info

    def _update_payment_channel(
        self,
        project_uuid: str,
        channel_uuid: str,
        channel_info: Dict[str, str],
        private_key_pem: str,
    ) -> None:
        response = self.payment_service.update_channel(
            channel_uuid=channel_uuid,
            private_key_pem=private_key_pem,
            phone_number=channel_info["phone_number"],
            project_uuid=project_uuid,
            phone_number_id=channel_info["phone_number_id"],
            waba_id=channel_info["waba_id"],
        )
        if response is None:
            raise OneClickPaymentConfigError(
                f"Failed to update payment channel "
                f"channel_uuid={channel_uuid} project={project_uuid}"
            )

    def _register_public_key(self, phone_number_id: str, keys: RSAKeyPair) -> None:
        try:
            self.meta_service.register_public_key(
                phone_number_id=phone_number_id,
                public_key_pem=keys.public_key_pem,
            )
        except CustomAPIException as exc:
            raise OneClickPaymentConfigError(
                f"Failed to register public key on Meta for "
                f"phone_number_id={phone_number_id}: {exc}"
            ) from exc

    def _create_meta_flow(
        self, waba_id: str, channel_uuid: str, endpoint_uri: str
    ) -> Dict[str, Any]:
        try:
            flow = self.meta_service.create_flow(
                waba_id=waba_id,
                name=settings.PAYMENT_FLOW_NAME,
                categories=PAYMENT_FLOW_CATEGORIES,
                endpoint_uri=endpoint_uri,
                flow_json=build_payment_flow_json(),
            )
        except CustomAPIException as exc:
            raise OneClickPaymentConfigError(
                f"Failed to create Meta Flow for waba_id={waba_id} "
                f"channel_uuid={channel_uuid}: {exc}"
            ) from exc

        if not flow or not flow.get("id"):
            raise OneClickPaymentConfigError(
                f"Meta Flow creation returned no id for waba_id={waba_id} "
                f"channel_uuid={channel_uuid}"
            )

        return flow

    def _publish_flow(self, flow_id: str) -> None:
        try:
            response = self.meta_service.publish_flow(flow_id)
        except CustomAPIException as exc:
            raise OneClickPaymentConfigError(
                f"Failed to publish Meta Flow flow_id={flow_id}: {exc}"
            ) from exc

        # Meta may answer 200 OK with {"success": false} on partial
        # failures, so we explicitly require the success flag instead
        # of relying on the HTTP status alone.
        if not (response or {}).get("success"):
            raise OneClickPaymentConfigError(
                f"Meta publish for flow_id={flow_id} did not report success: "
                f"response={response}"
            )

    @staticmethod
    def _build_payment_webhook_url(channel_uuid: str) -> str:
        base_url = (settings.PAYMENT_REST_ENDPOINT or "").rstrip("/")
        if not base_url:
            raise OneClickPaymentConfigError("PAYMENT_REST_ENDPOINT is not configured.")
        return f"{base_url}/v1/channels/{channel_uuid}/meta/webhook"

    @staticmethod
    def _persist_flow_created(
        onboarding: ProjectOnboarding,
        channel_uuid: str,
        flow_id: str,
    ) -> None:
        """Persists the newly created flow id with ``published=False``.

        Done immediately after a successful create_flow so a later
        publish failure can be retried without recreating the flow.
        """
        config = onboarding.config or {}
        wpp_cloud = config.setdefault("channels", {}).setdefault("wpp-cloud", {})
        wpp_cloud["payment"] = {
            "channel_uuid": channel_uuid,
            "flow_id": flow_id,
            "published": False,
        }
        onboarding.config = config
        onboarding.save(update_fields=["config"])

    @staticmethod
    def _mark_flow_published(onboarding: ProjectOnboarding) -> None:
        """Flips ``payment.published`` to True after a successful publish."""
        config = onboarding.config or {}
        payment = config["channels"]["wpp-cloud"]["payment"]
        payment["published"] = True
        onboarding.config = config
        onboarding.save(update_fields=["config"])
