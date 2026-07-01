from django.test import TestCase

from retail.webhooks.vtex.serializers import (
    CartSerializer,
    ExternalAbandonedCartSerializer,
)


class TestCartSerializer(TestCase):
    """
    Direct validation tests for `CartSerializer`.

    The abandoned cart view currently mocks this serializer in most tests, so
    these cases exercise the real fields
    without going through the view.
    """

    def setUp(self):
        self.valid_payload = {
            "account": "test-account",
            "cart_id": "order-123",
            "phone": "5584987654321",
            "name": "Test User",
        }

    def test_valid_payload_parses_all_five_fields(self):
        serializer = CartSerializer(data=self.valid_payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)

        validated = serializer.validated_data
        self.assertEqual(validated["account"], "test-account")
        self.assertEqual(validated["cart_id"], "order-123")
        self.assertEqual(validated["phone"], "5584987654321")
        self.assertEqual(validated["name"], "Test User")
        self.assertEqual(
            set(validated.keys()),
            {"account", "cart_id", "phone", "name"},
        )

    def test_missing_account_is_invalid(self):
        payload = dict(self.valid_payload)
        del payload["account"]

        serializer = CartSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("account", serializer.errors)

    def test_missing_cart_id_is_invalid(self):
        payload = dict(self.valid_payload)
        del payload["cart_id"]

        serializer = CartSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("cart_id", serializer.errors)

    def test_missing_phone_is_invalid(self):
        payload = dict(self.valid_payload)
        del payload["phone"]

        serializer = CartSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("phone", serializer.errors)

    def test_missing_name_is_invalid(self):
        payload = dict(self.valid_payload)
        del payload["name"]

        serializer = CartSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("name", serializer.errors)

    def test_empty_payload_reports_every_field(self):
        serializer = CartSerializer(data={})

        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            set(serializer.errors.keys()),
            {"account", "cart_id", "phone", "name"},
        )

    def test_extra_fields_are_ignored(self):
        payload = dict(self.valid_payload)
        payload["unexpected"] = "ignored"

        serializer = CartSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("unexpected", serializer.validated_data)


class TestExternalAbandonedCartSerializer(TestCase):
    def setUp(self):
        self.valid_payload = {
            "cart_id": "order-123",
            "phone": "5584987654321",
            "name": "Test User",
        }

    def test_valid_payload_parses_required_fields(self):
        serializer = ExternalAbandonedCartSerializer(data=self.valid_payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            set(serializer.validated_data.keys()),
            {"cart_id", "phone", "name"},
        )

    def test_account_field_is_not_accepted(self):
        payload = dict(self.valid_payload)
        payload["account"] = "spoofed-account"

        serializer = ExternalAbandonedCartSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("account", serializer.validated_data)

    def test_missing_cart_id_is_invalid(self):
        payload = dict(self.valid_payload)
        del payload["cart_id"]

        serializer = ExternalAbandonedCartSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("cart_id", serializer.errors)

    def test_missing_phone_is_invalid(self):
        payload = dict(self.valid_payload)
        del payload["phone"]

        serializer = ExternalAbandonedCartSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("phone", serializer.errors)

    def test_missing_name_is_invalid(self):
        payload = dict(self.valid_payload)
        del payload["name"]

        serializer = ExternalAbandonedCartSerializer(data=payload)

        self.assertFalse(serializer.is_valid())
        self.assertIn("name", serializer.errors)

    def test_empty_payload_reports_every_field(self):
        serializer = ExternalAbandonedCartSerializer(data={})

        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            set(serializer.errors.keys()),
            {"cart_id", "phone", "name"},
        )
