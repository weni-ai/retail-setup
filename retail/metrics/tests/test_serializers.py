from django.test import TestCase

from retail.metrics.constants import PRODUCT_METRIC_EVENT_TYPES, SUGGESTED_PLANS
from retail.metrics.serializers import RecordProductMetricEventSerializer


class RecordProductMetricEventSerializerTests(TestCase):
    def test_accepts_each_event_type(self):
        for event_type in PRODUCT_METRIC_EVENT_TYPES:
            serializer = RecordProductMetricEventSerializer(
                data={"event_type": event_type}
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertEqual(serializer.validated_data["event_type"], event_type)
            self.assertNotIn("suggested_plan", serializer.validated_data)

    def test_rejects_unknown_event_type(self):
        serializer = RecordProductMetricEventSerializer(
            data={"event_type": "unknown_click"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("event_type", serializer.errors)

    def test_accepts_each_suggested_plan(self):
        for plan in SUGGESTED_PLANS:
            serializer = RecordProductMetricEventSerializer(
                data={"event_type": "billing_subscribe", "suggested_plan": plan}
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertEqual(serializer.validated_data["suggested_plan"], plan)

    def test_rejects_unknown_suggested_plan(self):
        serializer = RecordProductMetricEventSerializer(
            data={"event_type": "billing_subscribe", "suggested_plan": "enterprise"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("suggested_plan", serializer.errors)

    def test_ignores_identity_fields_in_the_body(self):
        serializer = RecordProductMetricEventSerializer(
            data={
                "event_type": "help_whatsapp",
                "user_email": "other@example.com",
                "vtex_account": "other-store",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("user_email", serializer.validated_data)
        self.assertNotIn("vtex_account", serializer.validated_data)
