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
