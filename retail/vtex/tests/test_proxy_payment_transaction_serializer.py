from django.test import TestCase

from retail.vtex.serializers import ProxyPaymentTransactionSerializer


class TestProxyPaymentTransactionSerializer(TestCase):
    def setUp(self):
        self.valid_payload = {
            "transaction_id": "ABC123",
            "payments": [{"paymentSystem": "2", "value": 1000}],
        }

    def test_valid_minimal_payload(self):
        serializer = ProxyPaymentTransactionSerializer(data=self.valid_payload)
        self.assertTrue(serializer.is_valid())

    def test_merchant_name_is_optional(self):
        serializer = ProxyPaymentTransactionSerializer(data=self.valid_payload)
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("merchant_name"))

    def test_accepts_merchant_name(self):
        serializer = ProxyPaymentTransactionSerializer(
            data={**self.valid_payload, "merchant_name": "otherstore"}
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["merchant_name"], "otherstore")

    def test_merchant_name_accepts_null(self):
        serializer = ProxyPaymentTransactionSerializer(
            data={**self.valid_payload, "merchant_name": None}
        )
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("merchant_name"))
