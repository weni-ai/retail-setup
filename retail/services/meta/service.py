import logging

from typing import Any, Dict, List, Optional

from retail.clients.exceptions import CustomAPIException
from retail.interfaces.services.meta import MetaServiceInterface
from retail.interfaces.clients.meta.client import MetaClientInterface
from retail.clients.meta.client import MetaClient

logger = logging.getLogger(__name__)


class MetaService(MetaServiceInterface):
    def __init__(self, client: Optional[MetaClientInterface] = None):
        self.client = client or MetaClient()

    def get_pre_approved_template(
        self, template_name: str, language: str
    ) -> Dict[str, Any]:
        return self.client.get_pre_approved_template(template_name, language)

    def fetch_library_template_by_name_and_language(
        self, template_name: str, language: str
    ) -> Optional[Dict[str, Any]]:
        """Return the exact-match library template, or ``None`` on failure.

        Wraps the client's exact-match fetch and is the boundary that
        swallows infrastructure exceptions per
        ``contracts/meta-library-catalog.md`` §4: HTTP failures
        (auth, rate limit, server errors) and malformed-JSON parsing
        errors collapse to ``None`` here so the use case sees a single
        deterministic return shape.
        """
        try:
            return self.client.fetch_library_template_by_name_and_language(
                template_name, language
            )
        except CustomAPIException as exc:
            logger.error(
                f"[Meta] library_template_fetch_failed: "
                f"template_name={template_name} language={language} "
                f"status={exc.status_code} detail={exc}"
            )
            return None
        except Exception as exc:
            logger.error(
                f"[Meta] library_template_fetch_unexpected_error: "
                f"template_name={template_name} language={language} "
                f"error={exc}"
            )
            return None

    def create_flow(
        self,
        waba_id: str,
        name: str,
        categories: List[str],
        endpoint_uri: str,
        flow_json: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.client.create_flow(
            waba_id=waba_id,
            name=name,
            categories=categories,
            endpoint_uri=endpoint_uri,
            flow_json=flow_json,
        )

    def register_public_key(
        self, phone_number_id: str, public_key_pem: str
    ) -> Dict[str, Any]:
        return self.client.register_public_key(phone_number_id, public_key_pem)

    def publish_flow(self, flow_id: str) -> Dict[str, Any]:
        return self.client.publish_flow(flow_id)

    def submit_template_sample(
        self, waba_id: str, sample_body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Delegate the ``message_samples`` call to the client and
        PROPAGATE every exception unmodified.
        """
        return self.client.submit_template_sample(waba_id, sample_body)
