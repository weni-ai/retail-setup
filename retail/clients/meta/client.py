from django.conf import settings

from typing import Dict, Optional

from retail.interfaces.clients.meta.client import MetaClientInterface
from retail.clients.base import RequestClient


class MetaClient(MetaClientInterface, RequestClient):
    def __init__(self, token: Optional[str] = None, url: Optional[str] = None):
        self.token = token or settings.META_SYSTEM_USER_ACCESS_TOKEN
        self.url = url or settings.META_API_URL

    def get_pre_approved_template(self, template_name: str) -> Dict[str, any]:
        url = f"{self.url}/message_template_library/"

        params = {
            "search": template_name,
            "language": "pt_BR",
        }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        response = self.make_request(
            url=url, method="GET", params=params, headers=headers
        )

        return response.json()
