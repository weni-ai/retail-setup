"""Legacy broadcast payload snapshot tests (T033 — US4 / FR-015 / SC-004).

Pins the EXACT byte-shape of the Flows broadcast payload emitted today by
``Broadcast.build_broadcast_template_message`` for the three template
families exercised by the OrderStatus fleet — body-only with positional
variables, image-header (s3-keyed) plus URL button, and image-header
(direct URL) plus PAYMENT_REQUEST buttons with ``order_details``. The
Direct Send feature MUST NOT alter any of these shapes; any byte drift
fails the snapshot and is treated as a regression
(``contracts/messaging-gateway-payload.md`` §2).
"""

from unittest.mock import MagicMock

from django.test import TestCase

from retail.agents.domains.agent_webhook.services.broadcast import Broadcast


_CHANNEL_UUID = "1f3a9c2a-fe4b-4d61-9f17-7b3a4d619f17"
_PROJECT_UUID = "9c2a1f3a-7b3a-4d61-9f17-fe4b2c2a1f3a"
_CONTACT_URN = "whatsapp:5598123456789"


class LegacyBroadcastPayloadSnapshotTest(TestCase):
    """FR-015 / SC-004 — legacy ``msg`` body MUST stay byte-identical.

    The three scenarios below cover the OrderStatus template families
    in production today: body-only with positional variables, image
    header (s3-keyed) plus URL button, and image header (direct URL)
    plus PAYMENT_REQUEST buttons combined with ``order_details``.

    Each snapshot is the FULL expected message dict — keys, values,
    types and array order are pinned (key ordering MAY differ per the
    spec's "byte-identical" definition). A future change that adds or
    removes any field on the legacy path will fail one of these tests.
    """

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())

    def _make_template(self, *, template_name: str, header: dict = None):
        template = MagicMock()
        template.current_version.template_name = template_name
        template.metadata = {"header": header} if header is not None else {}
        return template

    def test_body_only_with_positional_variables(self):
        """Scenario (a) — body + positional variables, no header / no buttons.

        T116(g) / T117(g) — the FR-014c / FR-014d wire-shape rules are
        Direct-Send-only. The legacy payload MUST continue to carry
        ``msg.template = {name, locale, variables}`` byte-for-byte and
        MUST NOT leak ``msg.direct_send_template_name`` or ``msg.text``
        onto the legacy cohort.
        """
        template = self._make_template(template_name="weni_order_invoiced_1700000000")
        data = {
            "template_variables": {"1": "Maria", "2": "12345"},
            "contact_urn": _CONTACT_URN,
            "language": "pt-BR",
        }

        result = self.handler.build_broadcast_template_message(
            data=data,
            channel_uuid=_CHANNEL_UUID,
            project_uuid=_PROJECT_UUID,
            template=template,
        )

        self.assertEqual(
            result,
            {
                "project": _PROJECT_UUID,
                "urns": [_CONTACT_URN],
                "channel": _CHANNEL_UUID,
                "msg": {
                    "template": {
                        "name": "weni_order_invoiced_1700000000",
                        "locale": "pt-BR",
                        "variables": ["Maria", "12345"],
                    },
                },
            },
        )
        self.assertNotIn("direct_send_template_name", result["msg"])
        self.assertNotIn("text", result["msg"])
        self.assertNotIn("direct_send", result["msg"])

    def test_image_header_s3_keyed_with_url_button_and_variables(self):
        """Scenario (b) — body + image header (s3-keyed) + ``url``-sub_type
        button + positional variables.

        The s3 key is resolved into a presigned URL by ``S3Service``; we
        inject a stub here so the snapshot can pin the literal output
        without the test depending on a real signing implementation.
        """
        template = self._make_template(
            template_name="weni_order_shipped_1700000000",
            header={"header_type": "IMAGE", "text": "orders/12345.jpg"},
        )
        s3_service = MagicMock()
        s3_service.generate_presigned_url.return_value = (
            "https://cdn.loja.com/orders/12345.jpg?token=PRESIGNED"
        )
        data = {
            "template_variables": {
                "1": "Maria",
                "2": "12345",
                "button": "12345",
            },
            "contact_urn": _CONTACT_URN,
            "language": "pt-BR",
        }

        result = self.handler.build_broadcast_template_message(
            data=data,
            channel_uuid=_CHANNEL_UUID,
            project_uuid=_PROJECT_UUID,
            template=template,
            s3_service=s3_service,
        )

        s3_service.generate_presigned_url.assert_called_once_with("orders/12345.jpg")
        self.assertEqual(
            result,
            {
                "project": _PROJECT_UUID,
                "urns": [_CONTACT_URN],
                "channel": _CHANNEL_UUID,
                "msg": {
                    "template": {
                        "name": "weni_order_shipped_1700000000",
                        "locale": "pt-BR",
                        "variables": ["Maria", "12345"],
                    },
                    "buttons": [
                        {
                            "sub_type": "url",
                            "parameters": [
                                {"type": "text", "text": "12345"},
                            ],
                        }
                    ],
                    "attachments": [
                        "image/jpeg:https://cdn.loja.com/orders/12345.jpg"
                        "?token=PRESIGNED"
                    ],
                },
            },
        )

    def test_image_header_direct_url_with_payment_buttons_and_order_details(self):
        """Scenario (c) — body + image header (direct URL) +
        ``payment_request``-sub_type buttons + ``interaction_type=order_details``
        + ``order_details`` payload.
        """
        template = self._make_template(
            template_name="weni_payment_pending_1700000000",
        )
        order_details = {
            "reference_id": "12345-01",
            "payment_settings": {
                "type": "digital-goods",
                "payment_link": "https://example.com/checkout",
                "pix_config": {
                    "key": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "key_type": "EVP",
                    "merchant_name": "TestStore",
                    "code": "00020126580014br.gov.bcb.pix",
                },
            },
            "total_amount": 26489,
            "order": {
                "items": [
                    {
                        "retailer_id": "880032#1",
                        "name": "Tenis Nike Air Max 270",
                        "amount": {"value": 24990, "offset": 100},
                        "quantity": 1,
                    }
                ],
                "subtotal": 26988,
                "tax": {"description": "Impostos", "offset": 100, "value": 0},
                "discount": {"description": "Desconto", "offset": 100, "value": 999},
                "shipping": {"description": "Frete", "offset": 100, "value": 500},
            },
        }
        payment_buttons = [
            {"type": "pix_dynamic_code", "text": "00020126580014br.gov.bcb.pix"},
            {"type": "payment_link", "text": "https://example.com/pay"},
        ]
        data = {
            "template_variables": {
                "1": "Roberta",
                "image_url": "https://cdn.loja.com/orders/12345.jpg",
                "order_details": order_details,
                "payment_buttons": payment_buttons,
            },
            "contact_urn": _CONTACT_URN,
            "language": "pt-BR",
        }

        result = self.handler.build_broadcast_template_message(
            data=data,
            channel_uuid=_CHANNEL_UUID,
            project_uuid=_PROJECT_UUID,
            template=template,
        )

        self.assertEqual(
            result,
            {
                "project": _PROJECT_UUID,
                "urns": [_CONTACT_URN],
                "channel": _CHANNEL_UUID,
                "msg": {
                    "template": {
                        "name": "weni_payment_pending_1700000000",
                        "locale": "pt-BR",
                        "variables": ["Roberta"],
                    },
                    "attachments": ["image/jpeg:https://cdn.loja.com/orders/12345.jpg"],
                    "interaction_type": "order_details",
                    "order_details": order_details,
                    "buttons": [
                        {
                            "sub_type": "payment_request",
                            "parameters": [
                                {
                                    "type": "pix_dynamic_code",
                                    "text": "00020126580014br.gov.bcb.pix",
                                }
                            ],
                        },
                        {
                            "sub_type": "payment_request",
                            "parameters": [
                                {
                                    "type": "payment_link",
                                    "text": "https://example.com/pay",
                                }
                            ],
                        },
                    ],
                },
            },
        )

    def test_body_only_without_language_omits_locale(self):
        """Edge case — when neither ``data["language"]`` nor
        ``template.metadata["language"]`` is set, the legacy shape omits
        the ``locale`` key entirely (it is conditionally added only when
        the language is resolvable). Pinning the absence guards against
        a future "default locale" injection that would silently change
        the wire shape.
        """
        template = self._make_template(template_name="weni_order_invoiced_no_locale")
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": _CONTACT_URN,
        }

        result = self.handler.build_broadcast_template_message(
            data=data,
            channel_uuid=_CHANNEL_UUID,
            project_uuid=_PROJECT_UUID,
            template=template,
        )

        self.assertEqual(
            result,
            {
                "project": _PROJECT_UUID,
                "urns": [_CONTACT_URN],
                "channel": _CHANNEL_UUID,
                "msg": {
                    "template": {
                        "name": "weni_order_invoiced_no_locale",
                        "variables": ["Maria"],
                    },
                },
            },
        )
