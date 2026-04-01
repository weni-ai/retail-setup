from django.test import TestCase

from retail.api.integrated_agent.serializers import SendTestTemplateSerializer


class SendTestTemplateSerializerTest(TestCase):
    def test_valid_data(self):
        data = {
            "contact_urns": ["whatsapp:5584999999999"],
            "agent": "abandoned_cart",
            "variables": ["var1", "var2"],
        }
        serializer = SendTestTemplateSerializer(data=data)

        self.assertTrue(serializer.is_valid())
        self.assertEqual(
            serializer.validated_data["contact_urns"], data["contact_urns"]
        )
        self.assertEqual(serializer.validated_data["agent"], data["agent"])
        self.assertEqual(serializer.validated_data["variables"], data["variables"])

    def test_valid_data_with_order_notification_agent(self):
        data = {
            "contact_urns": ["whatsapp:5584999999999"],
            "agent": "order_notification",
            "variables": [],
        }
        serializer = SendTestTemplateSerializer(data=data)

        self.assertTrue(serializer.is_valid())

    def test_valid_data_without_variables(self):
        data = {
            "contact_urns": ["whatsapp:5584999999999"],
            "agent": "abandoned_cart",
        }
        serializer = SendTestTemplateSerializer(data=data)

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["variables"], [])

    def test_valid_data_with_multiple_urns(self):
        data = {
            "contact_urns": [
                "whatsapp:5584999999999",
                "whatsapp:5584888888888",
            ],
            "agent": "abandoned_cart",
            "variables": ["var1"],
        }
        serializer = SendTestTemplateSerializer(data=data)

        self.assertTrue(serializer.is_valid())
        self.assertEqual(len(serializer.validated_data["contact_urns"]), 2)

    def test_invalid_empty_contact_urns(self):
        data = {
            "contact_urns": [],
            "agent": "abandoned_cart",
        }
        serializer = SendTestTemplateSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("contact_urns", serializer.errors)

    def test_invalid_missing_contact_urns(self):
        data = {
            "agent": "abandoned_cart",
        }
        serializer = SendTestTemplateSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("contact_urns", serializer.errors)

    def test_invalid_agent_choice(self):
        data = {
            "contact_urns": ["whatsapp:5584999999999"],
            "agent": "invalid_agent",
        }
        serializer = SendTestTemplateSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("agent", serializer.errors)

    def test_invalid_missing_agent(self):
        data = {
            "contact_urns": ["whatsapp:5584999999999"],
        }
        serializer = SendTestTemplateSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("agent", serializer.errors)
