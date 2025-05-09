from typing import Protocol, Dict, Any, Optional

from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface


class IntegrationsServiceInterface(Protocol):
    def __init__(self, client: IntegrationsClientInterface) -> None: ...

    def create_template(
        self,
        app_uuid: str,
        project_uuid: str,
        name: str,
        category: str,
        gallery_version: Optional[str] = None,
    ) -> str: ...

    def create_template_translation(
        self,
        app_uuid: str,
        project_uuid: str,
        template_uuid: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]: ...
