"""Client for connection with Integrations"""

import concurrent.futures

import logging

import math

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

    def fetch_templates_from_user(self, app_uuid: str) -> List[Dict]:
        def fetch_single_page(app_uuid: str, page: int, page_size: int = 15) -> Dict:
            print(f"Fetching page {page}")
            url = f"{self.base_url}/api/v1/apps/{app_uuid}/templates/?page={page}&page_size={page_size}"

            print(f"URL: {url}")

            response = self.make_request(
                url, method="GET", headers=self.authentication_instance.headers
            ).json()

            print(f"Response: {response}")

            return response

        print("Dentro do client do integrations")

        page_size = 15

        first_page_response = fetch_single_page(app_uuid, 1, page_size)

        all_templates = first_page_response.get("results", [])

        print(f"Templates encontrados: {all_templates}")

        total_count = first_page_response.get("count", 0)

        print(f"Total de templates: {total_count}")
        print(f"Page size: {page_size}")

        if total_count <= page_size:
            return all_templates

        total_pages = math.ceil(total_count / page_size)

        if total_pages > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_page = {
                    executor.submit(fetch_single_page, app_uuid, page, page_size): page
                    for page in range(2, total_pages + 1)
                }

                page_results = {}
                for future in concurrent.futures.as_completed(future_to_page):
                    page_num = future_to_page[future]
                    try:
                        page_response = future.result()
                        page_results[page_num] = page_response.get("results", [])
                    except Exception as exc:
                        logger.warning(f"Error fetching page {page_num}: {exc}")
                        page_results[page_num] = []

                for page_num in sorted(page_results.keys()):
                    all_templates.extend(page_results[page_num])

        return all_templates
