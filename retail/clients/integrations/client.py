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

    def create_template_message(
        self, app_uuid: str, project_uuid: str, name: str, category: str
    ) -> str:
        url = f"{self.base_url}/api/v1/apps/{app_uuid}/templates/"

        payload = {
            "name": name,
            "category": category,
            "text_preview": name,
            "project_uuid": project_uuid,
        }

        response = self.make_request(
            url,
            method="POST",
            json=payload,
            headers=self.authentication_instance.headers,
        )
        template_uuid = response.json().get("uuid")
        return template_uuid

    def create_template_translation(
        self, app_uuid: str, project_uuid: str, template_uuid: str, payload: dict
    ):
        payload["project_uuid"] = project_uuid

        url = f"{self.base_url}/api/v1/apps/{app_uuid}/templates/{template_uuid}/translations/"

        response = self.make_request(
            url,
            method="POST",
            json=payload,
            headers=self.authentication_instance.headers,
        )
        return response

    def create_library_template_message(
        self, app_uuid: str, project_uuid: str, template_data: dict
    ) -> str:
        """
        Sends a request to create a library template message in the external service.

        Args:
            app_uuid (str): The UUID of the application.
            project_uuid (str): The UUID of the project.
            template_data (dict): The template payload data.

        Returns:
            str: The response from the external service.
        """
        url = f"{self.base_url}/api/v1/apps/{app_uuid}/templates/create_library_templates/"

        # Add Project-Uuid to the headers
        headers = {
            **self.authentication_instance.headers,
            "Project-Uuid": project_uuid,
        }

        response = self.make_request(
            url,
            method="POST",
            json=template_data,
            headers=headers,
        )
        return response.json()
