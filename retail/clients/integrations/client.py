"""Client for connection with Integrations"""

from django.conf import settings

from retail.clients.base import RequestClient, InternalAuthentication
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface


class IntegrationsClient(RequestClient, IntegrationsClientInterface):
    def __init__(self):
        self.base_url = settings.INTEGRATIONS_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()

    def get_vtex_integration_detail(self, project_uuid):
        url = f"{self.base_url}/api/v1/apptypes/vtex/integration-details/{str(project_uuid)}"

        response = self.make_request(
            url, method="GET", headers=self.authentication_instance.headers
        )
        return response.json()
