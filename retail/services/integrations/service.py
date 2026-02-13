import logging

from typing import List, Optional, Dict, Any

from datetime import datetime

from retail.clients.exceptions import CustomAPIException
from retail.clients.integrations.client import IntegrationsClient
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface
from retail.agents.domains.agent_integration.usecases.build_abandoned_cart_translation import (
    BuildAbandonedCartTranslationUseCase,
)

logger = logging.getLogger(__name__)


class IntegrationsService:
    def __init__(self, client: Optional[IntegrationsClientInterface] = None):
        self.client = client or IntegrationsClient()

    def get_vtex_integration_detail(self, project_uuid: str) -> dict:
        """
        Retrieve the VTEX integration details for a given project UUID.
        Handles communication errors and returns None in case of failure.
        """
        try:
            return self.client.get_vtex_integration_detail(project_uuid)
        except CustomAPIException as e:
            print(
                f"Error {e.status_code} when retrieving VTEX integration for project {project_uuid}."
            )
            return None

    def create_abandoned_cart_template(
        self, app_uuid: str, project_uuid: str, domain: str
    ) -> str:
        """
        Creates an abandoned cart template and translations for multiple languages.

        This method creates translations for all available languages (pt_BR, en, es)
        using the centralized AbandonedCartTranslationBuilder.
        """
        try:
            # Format the current datetime
            current_datetime = datetime.now()
            formatted_datetime = current_datetime.strftime("%Y%m%d%H%M%S")

            template_name = f"weni_abandoned_cart_{formatted_datetime}"

            # Create Template
            template_uuid = self.client.create_template_message(
                app_uuid=app_uuid,
                project_uuid=project_uuid,
                name=template_name,
                category="MARKETING",
            )

            # Prepare translations for multiple languages using the translation builder
            button_url = f"https://{domain}/checkout?orderFormId=" + "{{1}}"
            button_url_example = f"https://{domain}/checkout?orderFormId=92421d4a70224658acaab0c172f6b6d7"

            # Get translations for all available languages
            available_languages = (
                BuildAbandonedCartTranslationUseCase.get_available_language_codes()
            )
            translations = [
                BuildAbandonedCartTranslationUseCase.build_integrations_translation(
                    language_code=lang_code,
                    button_url=button_url,
                    button_url_example=button_url_example,
                )
                for lang_code in available_languages
            ]

            # Create translations for each language
            for translation in translations:
                self.client.create_template_translation(
                    app_uuid=app_uuid,
                    project_uuid=project_uuid,
                    template_uuid=template_uuid,
                    payload=translation,
                )
                print(f"Translation created for language {translation['language']}.")

            return template_name

        except CustomAPIException as e:
            print(
                f"Error {e.status_code} during template or translation creation: {str(e)}"
            )
            raise

    def create_order_status_templates(
        self, app_uuid: str, project_uuid: str, store: str
    ) -> dict:
        """
        Creates order status templates in multiple languages and returns the template configuration.

        Args:
            app_uuid (str): The app UUID for Meta's API.
            project_uuid (str): The project UUID for integration.
            store (str): The base URL for the store.

        Returns:
            dict: A dictionary containing the template names and their respective UUIDs.
        """
        button_url = f"https://{store}/account#/orders/"
        button_url_example = f"https://{store}/account#/orders/1234567891230-01"
        # Format the current datetime
        current_datetime = datetime.now()
        formatted_datetime = current_datetime.strftime("%Y%m%d%H%M%S")

        # Define the templates and their base payloads
        templates = [
            {
                "status": "invoiced",
                "base_payload": {
                    "library_template_name": "purchase_receipt_1",
                    "name": f"weni_purchase_receipt_1_{formatted_datetime}",
                    "language": "pt_BR",
                    "category": "UTILITY",
                },
            },
            {
                "status": "payment-approved",
                "base_payload": {
                    "library_template_name": "payment_confirmation_2",
                    "name": f"weni_payment_confirmation_2_{formatted_datetime}",
                    "language": "pt_BR",
                    "category": "UTILITY",
                    "library_template_button_inputs": [
                        {
                            "type": "URL",
                            "url": {
                                "base_url": button_url,
                                "url_suffix_example": button_url_example,
                            },
                        }
                    ],
                },
            },
            {
                "status": "order-created",
                "base_payload": {
                    "library_template_name": "order_management_2",
                    "name": f"weni_order_management_2_{formatted_datetime}",
                    "language": "pt_BR",
                    "category": "UTILITY",
                    "library_template_button_inputs": [
                        {
                            "type": "URL",
                            "url": {
                                "base_url": button_url,
                                "url_suffix_example": button_url_example,
                            },
                        }
                    ],
                },
            },
            {
                "status": "canceled",
                "base_payload": {
                    "library_template_name": "order_canceled_3",
                    "name": f"weni_order_canceled_3_{formatted_datetime}",
                    "language": "pt_BR",
                    "category": "UTILITY",
                    "library_template_button_inputs": [
                        {
                            "type": "URL",
                            "url": {
                                "base_url": button_url,
                                "url_suffix_example": button_url_example,
                            },
                        }
                    ],
                },
            },
            {
                "status": "invoice-no-file",
                "base_payload": {
                    "library_template_name": "purchase_transaction_alert",
                    "name": f"weni_purchase_transaction_alert_{formatted_datetime}",
                    "language": "pt_BR",
                    "category": "UTILITY",
                },
            },
        ]

        # Languages to generate translations for each template
        languages = ["pt_BR", "en", "es"]

        created_templates = {}

        # Prepare all templates for sending in a single call
        library_templates = []

        for template in templates:
            template_name = template["base_payload"]["name"]
            template_status = template["status"]
            created_templates[template_status] = template_name
            library_templates.append(template["base_payload"])

        # Send all templates at once with languages list
        self.client.create_library_template_message(
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            template_data={
                "library_templates": library_templates,
                "languages": languages,
            },
        )

        return created_templates

    def get_synchronized_templates(self, app_uuid: str, template_list: list) -> str:
        """
        Get all synchronized templates for a given app UUID and determine their synchronization status.

        Args:
            app_uuid (str): The UUID of the application.
            template_list (list): List of template names to check.

        Returns:
            str: One of the following statuses:
                - "synchronized" → All templates exist and are approved.
                - "pending" → Some templates are missing or pending.
                - "rejected" → At least one template was rejected.
        """
        templates = self.client.get_synchronized_templates(app_uuid)

        # If no templates were synchronized yet, return "pending"
        if not templates:
            return "pending"

        for template in template_list:
            if template not in templates:
                return "pending"  # Missing template → still pending

            template_statuses = [t["status"] for t in templates[template]]

            if "REJECTED" in template_statuses:
                return "rejected"  # If any template is rejected, stop checking

            if any(status != "APPROVED" for status in template_statuses):
                return "pending"  # If any status is not approved, keep waiting

        return "synchronized"  # If all templates exist and are approved

    def create_template(
        self,
        app_uuid: str,
        project_uuid: str,
        name: str,
        category: str,
        gallery_version: Optional[str] = None,
    ) -> str:
        return self.client.create_template_message(
            app_uuid, project_uuid, name, category, gallery_version=gallery_version
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

    def create_library_template(
        self,
        app_uuid: str,
        project_uuid: str,
        template_data: Dict[str, Any],
    ) -> str:
        return self.client.create_library_template(
            app_uuid, project_uuid, template_data
        )

    def fetch_template_metrics(
        self,
        app_uuid: str,
        template_versions: List[str],
        start: str,
        end: str,
    ) -> dict:
        return self.client.fetch_template_metrics(
            app_uuid, template_versions, start, end
        )

    def fetch_templates_from_user(
        self,
        app_uuid: str,
        project_uuid: str,
        templates_names: List[str],
        language: str,
    ) -> Dict[str, Dict[str, Any]]:
        def adapt_translation_to_gallery_format(
            translation: Dict[str, Any], category: str
        ) -> Dict[str, Any]:
            return {
                "header": translation.get("header"),
                "body": translation.get("body"),
                "footer": translation.get("footer"),
                "buttons": [
                    {"type": b["button_type"], "url": b["url"]}
                    for b in translation.get("buttons", [])
                ],
                "body_params": translation.get("body_params"),
                "category": category,
                "language": language,
            }

        templates = self.client.fetch_templates_from_user(
            app_uuid, project_uuid, templates_names
        )

        translations_by_name = {}

        for template in templates:
            category = template.get("category")
            template_name = template.get("name")
            for translation in template.get("translations", []):
                if (
                    translation.get("language") == language
                    and translation.get("status") == "APPROVED"
                ):
                    translations_by_name[
                        template_name
                    ] = adapt_translation_to_gallery_format(translation, category)

        return translations_by_name

    def create_wwc_app(self, project_uuid: str, config: Dict) -> Optional[Dict]:
        """
        Creates a WWC (Weni Web Chat) app for the given project.

        Returns:
            Dict with created app data or None on failure.
        """
        try:
            return self.client.create_wwc_app(project_uuid, config)
        except CustomAPIException as e:
            logger.error(
                f"Error {e.status_code} when creating WWC app "
                f"for project {project_uuid}: {e}"
            )
            return None

    def configure_wwc_app(self, app_uuid: str, config: Dict) -> Optional[Dict]:
        """
        Configures a previously created WWC app.

        Returns:
            Dict with configured app data (uuid, script) or None on failure.
        """
        try:
            return self.client.configure_wwc_app(app_uuid, config)
        except CustomAPIException as e:
            logger.error(
                f"Error {e.status_code} when configuring WWC app " f"{app_uuid}: {e}"
            )
            return None
