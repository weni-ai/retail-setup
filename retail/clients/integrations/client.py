"""Client for connection with Integrations"""

from django.conf import settings

from retail.clients.base import RequestClient


class InternalAuthentication(RequestClient):
    def __get_module_token(self):
        data = {
            "client_id": settings.OIDC_RP_CLIENT_ID,
            "client_secret": settings.OIDC_RP_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }
        request = self.make_request(
            url=settings.OIDC_OP_TOKEN_ENDPOINT, method="POST", data=data
        )

        token = request.json().get("access_token")

        return f"Bearer {token}"

    @property
    def headers(self):
        return {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": self.__get_module_token(),
        }


class IntegrationsClient(RequestClient):
    def __init__(self):
        self.base_url = settings.INTEGRATIONS_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()

    def get_vtex_integration_detail(self, project_uuid):
        url = f"{self.base_url}/api/v1/apptypes/vtex/integration-details/{str(project_uuid)}"

        response = self.make_request(
            url, method="GET", headers=self.authentication_instance.headers
        )
        return response.json()
