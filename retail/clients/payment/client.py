"""HTTP client for the payment microservice.

Provides the channel-update call required by the One-Click Payment
configuration step (see ``ConfigureOneClickPaymentUseCase``).
"""

from typing import Any, Dict, Optional

from django.conf import settings

from retail.clients.base import RequestClient
from retail.interfaces.clients.payment.client import PaymentClientInterface
from retail.interfaces.jwt import JWTInterface
from retail.jwt_keys.usecases.generate_jwt import JWTUsecase


class PaymentClient(RequestClient, PaymentClientInterface):
    """
    HTTP client for the payment microservice.

    payment-ms authenticates inbound calls with a project-scoped JWT
    (the ``project_uuid`` is encoded in the token claims), so each
    request signs a fresh token for the current project rather than
    sharing a single internal credential.
    """

    def __init__(self, jwt_usecase: Optional[JWTInterface] = None):
        self.base_url = settings.PAYMENT_REST_ENDPOINT
        self.jwt_usecase = jwt_usecase or JWTUsecase()

    def _headers_for(self, project_uuid: str) -> Dict[str, str]:
        """
        Builds the auth headers expected by payment-ms for a project.

        Args:
            project_uuid: Project the request is acting on; used as
                the JWT subject claim.

        Returns:
            Dict with ``Authorization`` (project-scoped JWT) and
            ``Content-Type`` headers.
        """
        token = self.jwt_usecase.generate_jwt_token(project_uuid)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def update_channel(
        self,
        channel_uuid: str,
        private_key_pem: str,
        phone_number: str,
        project_uuid: str,
        phone_number_id: str,
        waba_id: str,
    ) -> Dict[str, Any]:
        """
        Persists WhatsApp channel credentials in the payment microservice.

        Mirrors the contract expressed in the Insomnia collection: a
        single PUT carries the private key plus the identifiers needed
        by payment-ms to bind the channel to the merchant's WABA.

        Args:
            channel_uuid: Flows channel uuid (acts as resource id at
                payment-ms ``/v1/channels/{channel_uuid}``).
            private_key_pem: PEM-encoded RSA private key generated for
                the WhatsApp Business Encryption flow.
            phone_number: WhatsApp display number (``+55 ...`` format).
            project_uuid: Owner project; also encoded in the JWT auth.
            phone_number_id: Meta Phone Number id.
            waba_id: WhatsApp Business Account id.

        Returns:
            Dict with payment-ms response.
        """
        url = f"{self.base_url}/v1/channels/{channel_uuid}"
        payload = {
            "private_key_pem": private_key_pem,
            "phone_number": phone_number,
            "project_uuid": project_uuid,
            "phone_number_id": phone_number_id,
            "waba_id": waba_id,
        }

        response = self.make_request(
            url=url,
            method="PUT",
            json=payload,
            headers=self._headers_for(project_uuid),
        )

        return response.json()
