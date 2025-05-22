from unittest import TestCase

from retail.agents.utils import build_broadcast_template_message


class TestBuildBroadcastTemplateMessage(TestCase):
    def setUp(self):
        self.channel_uuid = "3acb032f-c1db-4bd8-b33b-a43464a6accd"
        self.project_uuid = "95de8165-836e-4d9d-8ef4-abcf812cd546"

    def test_message_without_button(self):
        data = {
            "template": "order_confirmation",
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
            data, self.channel_uuid, self.project_uuid
        )
        self.assertEqual(result, expected)

    def test_message_with_button(self):
        data = {
            "template": "abandoned_cart",
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
            data, self.channel_uuid, self.project_uuid
        )
        self.assertEqual(result, expected)

    def test_non_numeric_keys_are_ignored(self):
        data = {
            "template": "test",
            "template_variables": {"1": "a", "abc": "should_be_ignored", "2": "b"},
            "contact_urn": "whatsapp:123",
            "language": "en-US",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid
        )
        self.assertEqual(result["msg"]["template"]["variables"], ["a", "b"])

    def test_default_language_fallback(self):
        data = {
            "template": "test",
            "template_variables": {"1": "only"},
            "contact_urn": "whatsapp:123",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid
        )
        self.assertEqual(result["msg"]["template"]["locale"], "pt-BR")

    def test_missing_locale_keeps_structure(self):
        data = {
            "template": "missing_locale",
            "template_variables": {"1": "Hello"},
            "contact_urn": "whatsapp:123",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid
        )
        self.assertIn("locale", result["msg"]["template"])
        self.assertEqual(result["msg"]["template"]["locale"], "pt-BR")

    def test_variable_ordering(self):
        data = {
            "template": "ordering_test",
            "template_variables": {"3": "third", "1": "first", "2": "second"},
            "contact_urn": "whatsapp:5511999999999",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid
        )

        self.assertEqual(
            result["msg"]["template"]["variables"],
            ["first", "second", "third"],
            "Variables should be ordered by numeric key ascending",
        )

    def test_empty_variables(self):
        data = {
            "template": "empty_case",
            "template_variables": {},
            "contact_urn": "whatsapp:999999999",
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid
        )
        self.assertEqual(result, {})  # Message should not be built without variables

    def test_missing_required_fields_returns_empty_dict(self):
        data = {
            "template_variables": {"1": "value"}
            # Missing both 'template' and 'contact_urn'
        }

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid
        )
        self.assertEqual(result, {})
