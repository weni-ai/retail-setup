from typing import Any, Dict, List, Optional, Protocol


class MetaClientInterface(Protocol):
    def get_pre_approved_template(
        self, template_name: str, language: str
    ) -> Dict[str, Any]:
        ...

    def fetch_library_template_by_name_and_language(
        self, template_name: str, language: str
    ) -> Optional[Dict[str, Any]]:
        ...

    def create_flow(
        self,
        waba_id: str,
        name: str,
        categories: List[str],
        endpoint_uri: str,
        flow_json: Dict[str, Any],
    ) -> Dict[str, Any]:
        ...

    def register_public_key(
        self, phone_number_id: str, public_key_pem: str
    ) -> Dict[str, Any]:
        ...

    def publish_flow(self, flow_id: str) -> Dict[str, Any]:
        ...

    def submit_template_sample(
        self, waba_id: str, sample_body: Dict[str, Any]
    ) -> Dict[str, Any]:
        ...
