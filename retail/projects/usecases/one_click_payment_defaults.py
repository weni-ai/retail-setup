"""Default Meta Flow definition for the One-Click Payment step.

The Flow body is rendered server-side and shipped to Meta during the
WhatsApp Cloud onboarding so the merchant's number can capture the
shopper's CVV in an encrypted single-screen flow. The actual decryption
runs on the payment microservice; this module only stores the static
shape that Meta accepts.
"""

from typing import Any, Dict, List


PAYMENT_FLOW_CATEGORIES: List[str] = ["SHOPPING"]


def build_payment_flow_json() -> Dict[str, Any]:
    """Returns the immutable Meta Flow JSON used for One-Click Payment.

    The body mirrors the contract negotiated with the payment-ms team
    (see ``payment.json`` Insomnia collection): a single terminal screen
    that asks for the CVV and posts it back via ``data_exchange``.
    """
    return {
        "routing_model": {"COLETAR_DADO": []},
        "data_api_version": "3.0",
        "version": "7.3",
        "screens": [
            {
                "id": "COLETAR_DADO",
                "title": "Confirmação",
                "terminal": True,
                "data": {
                    "final_cartao": {
                        "type": "string",
                        "__example__": "1234",
                    },
                    "valor_pedido": {
                        "type": "string",
                        "__example__": "R$ 150,00",
                    },
                },
                "layout": {
                    "type": "SingleColumnLayout",
                    "children": [
                        {
                            "type": "TextHeading",
                            "text": "Ambiente Seguro",
                        },
                        {
                            "type": "TextBody",
                            "text": (
                                "Para finalizar o pedido de "
                                "${data.valor_pedido} no cartão final "
                                "${data.final_cartao}, digite seu código "
                                "de confirmação."
                            ),
                        },
                        {
                            "type": "TextInput",
                            "name": "codigo_confirmacao",
                            "label": "CVV",
                            "input-type": "password",
                            "required": True,
                            "helper-text": "Clique no campo acima para digitar",
                        },
                        {
                            "type": "Footer",
                            "label": "Continuar",
                            "on-click-action": {
                                "name": "data_exchange",
                                "payload": {
                                    "cvv": "${form.codigo_confirmacao}",
                                },
                            },
                        },
                    ],
                },
            }
        ],
    }
