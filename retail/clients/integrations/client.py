"""Client for connection with Integrations"""

import logging

from django.conf import settings

from typing import Dict, List, Optional

from retail.clients.base import RequestClient, InternalAuthentication
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface

logger = logging.getLogger(__name__)


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
        self,
        app_uuid: str,
        project_uuid: str,
        name: str,
        category: str,
        gallery_version: Optional[str] = None,
    ) -> str:
        url = f"{self.base_url}/api/v1/apps/{app_uuid}/templates/"

        payload = {
            "name": name,
            "category": category,
            "text_preview": name,
            "project_uuid": project_uuid,
        }

        if gallery_version:
            payload["gallery_version"] = gallery_version

        # Log the template data # TODO: remove this
        print(f"Creating template with data: {payload}")
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

        # Log the template data # TODO: remove this
        print(f"Creating template translation with data: {payload}")
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
        url = f"{self.base_url}/api/v1/apps/{app_uuid}/templates/create-library-templates/"

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

    def get_synchronized_templates(self, app_uuid: str) -> dict:
        """
        Get all templates from paginated API and return a dictionary of templates with their translations.

        Args:
            app_uuid (str): The UUID of the application

        Returns:
            dict: Dictionary containing templates where key is template name and value is list of translations
        """
        templates_dict = {}
        page = 1

        while True:
            url = f"{self.base_url}/api/v1/apps/{app_uuid}/templates/?page={page}&page_size=15"

            response = self.make_request(
                url, method="GET", headers=self.authentication_instance.headers
            ).json()

            # Add templates from current page to dictionary
            for template in response["results"]:
                templates_dict[template["name"]] = template["translations"]

            # Check if there are more pages
            if not response["next"]:
                break

            page += 1

        return templates_dict

    def create_library_template(
        self, app_uuid: str, project_uuid: str, template_data: dict
    ) -> str:
        url = (
            f"{self.base_url}/api/v1/apps/{app_uuid}/templates/create-library-template/"
        )

        # Add Project-Uuid to the headers
        headers = {
            **self.authentication_instance.headers,
            "Project-Uuid": project_uuid,
        }

        # Log the template data # TODO: remove this
        print(f"Creating library template with data: {template_data}")

        response = self.make_request(
            url,
            method="POST",
            json=template_data,
            headers=headers,
        )
        return response.json()

    def fetch_template_metrics(
        self, app_uuid: str, template_versions: List[str], start: str, end: str
    ) -> Dict:
        url = f"{self.base_url}/api/v1/apptypes/wpp-cloud/apps/{app_uuid}/template-metrics/"
        payload = {
            "template_versions": template_versions,
            "start": start,
            "end": end,
        }
        response = self.make_request(
            url,
            method="POST",
            json=payload,
            headers=self.authentication_instance.headers,
        )

        return response.json()

    def fetch_templates_from_user(
        self,
        app_uuid: str,
        project_uuid: str,
        template_names: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Fetch templates from user with optional filtering by template names.
        Uses simple sequential pagination instead of multi-threading.
        """

        def fetch_single_page(
            app_uuid: str,
            page: int,
            page_size: int = 15,
            template_names: Optional[List[str]] = None,
        ) -> Dict:
            url = f"{self.base_url}/api/v1/apps/{app_uuid}/templates/"

            # Build query parameters
            params = {"page": page, "page_size": page_size}

            # Add template names filtering if provided
            if template_names:
                params["names"] = template_names

            headers = {
                **self.authentication_instance.headers,
                "Project-Uuid": project_uuid,
            }

            response = self.make_request(
                url, method="GET", headers=headers, params=params
            ).json()

            return response

        page_size = 15
        all_templates = []
        page = 1
        max_pages = 100  # Safety limit to prevent infinite loops

        while page <= max_pages:
            response = fetch_single_page(app_uuid, page, page_size, template_names)
            results = response.get("results", [])
            all_templates.extend(results)

            # If no more pages or no results, break
            if not response.get("next") or not results:
                break

            page += 1

        # Log warning if we hit the safety limit
        if page > max_pages:
            logger.warning(
                f"Reached maximum page limit ({max_pages}) for templates fetch. Some templates may be missing."
            )

        return all_templates
