from typing import Any, Dict, List, Optional

from retail.interfaces.services.meta import MetaServiceInterface
from retail.interfaces.clients.meta.client import MetaClientInterface
from retail.clients.meta.client import MetaClient


class MetaService(MetaServiceInterface):
    def __init__(self, client: Optional[MetaClientInterface] = None):
        self.client = client or MetaClient()

    def get_pre_approved_template(
        self, template_name: str, language: str
    ) -> Dict[str, Any]:
        return self.client.get_pre_approved_template(template_name, language)

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
