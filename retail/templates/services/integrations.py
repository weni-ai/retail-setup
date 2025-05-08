from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface
from retail.interfaces.services.integrations import IntegrationsServiceInterface
from retail.clients.integrations.client import IntegrationsClient

from typing import Optional, Dict, Any


class IntegrationsService(IntegrationsServiceInterface):
    def __init__(self, client: Optional[IntegrationsClientInterface] = None):
        self.client = client or IntegrationsClient()

    def create_template(
        self, app_uuid: str, project_uuid: str, name: str, category: str
    ) -> str:
        return self.client.create_template_message(
            app_uuid, project_uuid, name, category
        )

    def create_template_translation(
        self,
        app_uuid: str,
        project_uuid: str,
        template_uuid: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.client.create_template_translation(
            app_uuid, project_uuid, template_uuid, payload
        )
