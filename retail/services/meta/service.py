from typing import Optional, Dict

from retail.interfaces.services.meta import MetaServiceInterface
from retail.interfaces.clients.meta.client import MetaClientInterface
from retail.clients.meta.client import MetaClient


class MetaService(MetaServiceInterface):
    def __init__(self, client: Optional[MetaClientInterface] = None):
        self.client = client or MetaClient()

    def get_pre_approved_template(
        self, template_name: str, language: str
    ) -> Dict[str, any]:
        return self.client.get_pre_approved_template(template_name, language)
