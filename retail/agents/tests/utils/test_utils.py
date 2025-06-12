from unittest import TestCase
from retail.agents.utils import (
    build_broadcast_template_message,
    adapt_order_status_to_webhook_payload,
)
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


class TestBuildBroadcastTemplateMessage(TestCase):
    def setUp(self):
        self.channel_uuid = "3acb032f-c1db-4bd8-b33b-a43464a6accd"
        self.project_uuid = "95de8165-836e-4d9d-8ef4-abcf812cd546"

    def test_message_without_button(self):
        data = {
            "template_variables": {"2": "12345", "1": "@contact.name"},
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        expected = {
            "project": self.project_uuid,
            "urns": ["whatsapp:5565992828858"],
            "channel": self.channel_uuid,
            "msg": {
                "template": {
                    "locale": "pt-BR",
                    "name": "order_confirmation",
                    "variables": ["@contact.name", "12345"],
                }
            },
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "order_confirmation"
        )
        self.assertEqual(result, expected)

    def test_message_with_button(self):
        data = {
            "template_variables": {
                "1": "@contact.name",
                "button": "2960629205a149fd88f2d080d5affe25/",
            },
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        expected = {
            "project": self.project_uuid,
            "urns": ["whatsapp:5565992828858"],
            "channel": self.channel_uuid,
            "msg": {
                "template": {
                    "locale": "pt-BR",
                    "name": "abandoned_cart",
                    "variables": ["@contact.name"],
                },
                "buttons": [
                    {
                        "sub_type": "url",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "2960629205a149fd88f2d080d5affe25/",
                            }
                        ],
                    }
                ],
            },
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "abandoned_cart"
        )
        self.assertEqual(result, expected)

    def test_non_numeric_keys_are_ignored(self):
        data = {
            "template_variables": {"1": "a", "abc": "should_be_ignored", "2": "b"},
            "contact_urn": "whatsapp:123",
            "language": "en-US",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "test"
        )
        self.assertEqual(result["msg"]["template"]["variables"], ["a", "b"])

    def test_default_language_fallback(self):
        data = {
            "template_variables": {"1": "only"},
            "contact_urn": "whatsapp:123",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "test"
        )
        self.assertEqual(result["msg"]["template"]["locale"], "pt-BR")

    def test_missing_locale_keeps_structure(self):
        data = {
            "template_variables": {"1": "Hello"},
            "contact_urn": "whatsapp:123",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "missing_locale"
        )
        self.assertIn("locale", result["msg"]["template"])
        self.assertEqual(result["msg"]["template"]["locale"], "pt-BR")

    def test_variable_ordering(self):
        data = {
            "template_variables": {"3": "third", "1": "first", "2": "second"},
            "contact_urn": "whatsapp:5511999999999",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "ordering_test"
        )

        self.assertEqual(
            result["msg"]["template"]["variables"],
            ["first", "second", "third"],
            "Variables should be ordered by numeric key ascending",
        )

    def test_empty_variables(self):
        data = {
            "template_variables": {},
            "contact_urn": "whatsapp:999999999",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "empty_case"
        )
        self.assertEqual(result, {})  # Message should not be built without variables

    def test_missing_required_fields_returns_empty_dict(self):
        data = {
            "template_variables": {"1": "value"}
            # Missing 'contact_urn'
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "test"
        )
        self.assertEqual(result, {})

    def test_missing_template_name_returns_empty_dict(self):
        data = {
            "template_variables": {"1": "value"},
            "contact_urn": "whatsapp:123",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, ""
        )
        self.assertEqual(result, {})

    def test_missing_contact_urn_returns_empty_dict(self):
        data = {
            "template_variables": {"1": "value"},
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "test_template"
        )
        self.assertEqual(result, {})

    def test_none_contact_urn_returns_empty_dict(self):
        data = {
            "template_variables": {"1": "value"},
            "contact_urn": None,
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "test_template"
        )
        self.assertEqual(result, {})

    def test_none_template_name_returns_empty_dict(self):
        data = {
            "template_variables": {"1": "value"},
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, None
        )
        self.assertEqual(result, {})

    def test_button_with_empty_string_is_ignored(self):
        data = {
            "template_variables": {
                "1": "test",
                "button": "",
            },
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "test_template"
        )
        self.assertNotIn("buttons", result["msg"])

    def test_button_with_none_is_ignored(self):
        data = {
            "template_variables": {
                "1": "test",
                "button": None,
            },
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "test_template"
        )
        self.assertNotIn("buttons", result["msg"])

    def test_mixed_numeric_and_non_numeric_keys(self):
        data = {
            "template_variables": {
                "1": "first",
                "invalid": "ignored",
                "3": "third",
                "another_invalid": "also_ignored",
                "2": "second",
            },
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "test_template"
        )
        self.assertEqual(
            result["msg"]["template"]["variables"], ["first", "second", "third"]
        )

    def test_numeric_keys_with_gaps(self):
        data = {
            "template_variables": {
                "1": "first",
                "5": "fifth",
                "3": "third",
            },
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, "test_template"
        )
        self.assertEqual(
            result["msg"]["template"]["variables"], ["first", "third", "fifth"]
        )


class TestAdaptOrderStatusToWebhookPayload(TestCase):
    def test_adapt_order_status_to_webhook_payload(self):
        order_status_dto = OrderStatusDTO(
            domain="test.domain.com",
            orderId="12345",
            currentState="invoiced",
            lastState="payment-approved",
            vtexAccount="testaccount",
            recorder="test_recorder",
            currentChangeDate="2023-01-01T00:00:00Z",
            lastChangeDate="2023-01-01T00:00:00Z",
        )

        expected = {
            "Domain": "test.domain.com",
            "OrderId": "12345",
            "State": "invoiced",
            "LastState": "payment-approved",
            "Origin": {
                "Account": "testaccount",
                "Sender": "Gallery",
            },
        }

        result = adapt_order_status_to_webhook_payload(order_status_dto)
        self.assertEqual(result, expected)

    def test_adapt_order_status_with_empty_values(self):
        order_status_dto = OrderStatusDTO(
            domain="",
            orderId="",
            currentState="",
            lastState="",
            vtexAccount="",
            recorder="",
            currentChangeDate="",
            lastChangeDate="",
        )

        expected = {
            "Domain": "",
            "OrderId": "",
            "State": "",
            "LastState": "",
            "Origin": {
                "Account": "",
                "Sender": "Gallery",
            },
        }

        result = adapt_order_status_to_webhook_payload(order_status_dto)
        self.assertEqual(result, expected)

    def test_adapt_order_status_with_none_values(self):
        order_status_dto = OrderStatusDTO(
            domain=None,
            orderId=None,
            currentState=None,
            lastState=None,
            vtexAccount=None,
            recorder=None,
            currentChangeDate=None,
            lastChangeDate=None,
        )

        expected = {
            "Domain": None,
            "OrderId": None,
            "State": None,
            "LastState": None,
            "Origin": {
                "Account": None,
                "Sender": "Gallery",
            },
        }

        result = adapt_order_status_to_webhook_payload(order_status_dto)
        self.assertEqual(result, expected)

    def test_adapt_order_status_sender_is_always_gallery(self):
        order_status_dto = OrderStatusDTO(
            domain="test.domain.com",
            orderId="12345",
            currentState="invoiced",
            lastState="payment-approved",
            vtexAccount="testaccount",
            recorder="test_recorder",
            currentChangeDate="2023-01-01T00:00:00Z",
            lastChangeDate="2023-01-01T00:00:00Z",
        )

        result = adapt_order_status_to_webhook_payload(order_status_dto)
        self.assertEqual(result["Origin"]["Sender"], "Gallery")
