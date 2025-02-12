from retail.clients.exceptions import CustomAPIException
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface


class IntegrationsService:
    def __init__(self, client: IntegrationsClientInterface):
        self.client = client

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
        self, app_uuid: str, project_uuid: str, store: str
    ) -> str:
        """
        Creates an abandoned cart template and translations for multiple languages.
        """
        try:
            # Create Template
            template_name = "weni_abandoned_cart"
            template_uuid = self.client.create_template_message(
                app_uuid=app_uuid,
                project_uuid=project_uuid,
                name=template_name,
                category="MARKETING",
            )

            # Prepare translations for multiple languages
            button_url = f"https://{store}/checkout?orderFormId=" + "{{1}}"
            button_url_example = (
                f"https://{store}/checkout?orderFormId=92421d4a70224658acaab0c172f6b6d7"
            )
            translations = [
                {
                    "language": "pt_BR",
                    "body": {
                        "type": "BODY",
                        "text": (
                            "Olá, {{1}} vimos que você deixou itens no seu carrinho 🛒. "
                            "\nVamos fechar o pedido e garantir essas ofertas? "
                            "\n\nClique em Finalizar Pedido para concluir sua compra 👇"
                        ),
                        "example": {"body_text": [["João"]]},
                    },
                    "footer": {"type": "FOOTER", "text": "Finalizar Pedido"},
                    "buttons": [
                        {
                            "button_type": "URL",
                            "text": "Finalizar Pedido",
                            "url": button_url,
                            "example": [button_url_example],
                        },
                        {
                            "button_type": "QUICK_REPLY",
                            "text": "Parar Promoções",
                        },
                    ],
                },
                {
                    "language": "es",
                    "body": {
                        "type": "BODY",
                        "text": (
                            "Hola, {{1}} notamos que dejaste artículos en tu carrito 🛒. "
                            "\n¿Listo para completar tu pedido y asegurar estas ofertas? "
                            "\n\nHaz clic en Finalizar Pedido para completar tu compra 👇"
                        ),
                        "example": {"body_text": [["Juan"]]},
                    },
                    "footer": {"type": "FOOTER", "text": "Finalizar Pedido"},
                    "buttons": [
                        {
                            "button_type": "URL",
                            "text": "Finalizar Pedido",
                            "url": button_url,
                            "example": [button_url_example],
                        },
                        {
                            "button_type": "QUICK_REPLY",
                            "text": "Parar Promociones",
                        },
                    ],
                },
                {
                    "language": "en",
                    "body": {
                        "type": "BODY",
                        "text": (
                            "Hello, {{1}} we noticed you left items in your cart 🛒. "
                            "\nReady to complete your order and secure these deals? "
                            "\n\nClick Finish Order to complete your purchase 👇"
                        ),
                        "example": {"body_text": [["John"]]},
                    },
                    "footer": {"type": "FOOTER", "text": "Finish Order"},
                    "buttons": [
                        {
                            "button_type": "URL",
                            "text": "Finish Order",
                            "url": button_url,
                            "example": [button_url_example],
                        },
                        {
                            "button_type": "QUICK_REPLY",
                            "text": "Stop Promotions",
                        },
                    ],
                },
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

            return {"template_uuid": template_uuid, "template_name": template_name}

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
        # Define the templates and their base payloads
        templates = [
            {
                "status": "invoiced",
                "base_payload": {
                    "library_template_name": "purchase_receipt_1",
                    "name": "weni_purchase_receipt_1",
                    "language": "pt_BR",
                    "category": "UTILITY",
                },
            },
            {
                "status": "payment-approved",
                "base_payload": {
                    "library_template_name": "payment_confirmation_2",
                    "name": "weni_payment_confirmation_2",
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
                    "name": "weni_order_management_2",
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
                    "name": "weni_order_canceled_3",
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
                    "name": "weni_purchase_transaction_alert",
                    "language": "pt_BR",
                    "category": "UTILITY",
                },
            },
        ]

        # Languages to generate translations for each template
        languages = ["pt_BR", "en", "es"]

        # Final dictionary to store the template names and UUIDs
        created_templates = {}

        # Loop through each template and create them in all languages
        for template in templates:
            template_name = template["base_payload"]["name"]
            template_status = template["status"]

            for language in languages:
                payload = template["base_payload"].copy()
                payload["language"] = language  # Update the language for each iteration

                try:
                    # Call the service to create the template
                    self.client.create_library_template_message(
                        app_uuid=app_uuid,
                        project_uuid=project_uuid,
                        template_data=payload,
                    )

                    # Store the template name in the dictionary
                    created_templates[template_status] = template_name

                except CustomAPIException as e:
                    print(
                        f"Failed to create template '{template_name}' in {language}: {e}"
                    )
                    raise

        return created_templates
