"""Service wrapper around :class:`PaymentClient`.

Catches infrastructure errors and returns ``None`` so the calling use
case can surface a domain-specific failure instead of leaking
``CustomAPIException`` to the views/orchestrator.
"""

import logging
from typing import Any, Dict, Optional

from retail.clients.exceptions import CustomAPIException
from retail.clients.payment.client import PaymentClient
from retail.interfaces.clients.payment.client import PaymentClientInterface
from retail.interfaces.services.payment import PaymentServiceInterface

logger = logging.getLogger(__name__)


class PaymentService(PaymentServiceInterface):
    def __init__(self, client: Optional[PaymentClientInterface] = None):
        self.client = client or PaymentClient()

    def update_channel(
        self,
        channel_uuid: str,
        private_key_pem: str,
        phone_number: str,
        project_uuid: str,
        phone_number_id: str,
        waba_id: str,
    ) -> Optional[Dict[str, Any]]:
        try:
            return self.client.update_channel(
                channel_uuid=channel_uuid,
                private_key_pem=private_key_pem,
                phone_number=phone_number,
                project_uuid=project_uuid,
                phone_number_id=phone_number_id,
                waba_id=waba_id,
            )
        except CustomAPIException as exc:
            # Body intentionally omitted: payment-ms may echo the request
            # body in 4xx responses, which would leak the private key
            # into logs / Sentry. The status code is enough to triage;
            # the full payload is recoverable from the upstream service
            # logs when needed.
            logger.error(
                f"Error {exc.status_code} when updating payment channel "
                f"{channel_uuid} for project={project_uuid}"
            )
            return None
