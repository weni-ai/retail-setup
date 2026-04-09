from django.test import TestCase

from retail.vtex.serializers import PaymentGatewayProxySerializer


class TestPaymentGatewayProxySerializer(TestCase):
    def test_valid_minimal_payload(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "GET", "path": "/api/pvt/transactions/ABC123"}
        )
        self.assertTrue(serializer.is_valid())

    def test_valid_full_payload(self):
        serializer = PaymentGatewayProxySerializer(
            data={
                "method": "POST",
                "path": "/api/pvt/transactions/ABC123/payments",
                "headers": {"X-Custom": "value"},
                "data": {"key": "value"},
                "params": {"an": "teststore"},
            }
        )
        self.assertTrue(serializer.is_valid())

    def test_accepts_get_method(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "GET", "path": "/some/path"}
        )
        self.assertTrue(serializer.is_valid())

    def test_accepts_post_method(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "POST", "path": "/some/path"}
        )
        self.assertTrue(serializer.is_valid())

    def test_accepts_put_method(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "PUT", "path": "/some/path"}
        )
        self.assertTrue(serializer.is_valid())

    def test_rejects_patch_method(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "PATCH", "path": "/some/path"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("method", serializer.errors)

    def test_rejects_delete_method(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "DELETE", "path": "/some/path"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("method", serializer.errors)

    def test_method_is_required(self):
        serializer = PaymentGatewayProxySerializer(data={"path": "/some/path"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("method", serializer.errors)

    def test_path_is_required(self):
        serializer = PaymentGatewayProxySerializer(data={"method": "GET"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("path", serializer.errors)

    def test_headers_is_optional(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "GET", "path": "/some/path"}
        )
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("headers"))

    def test_data_is_optional(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "GET", "path": "/some/path"}
        )
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("data"))

    def test_params_is_optional(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "GET", "path": "/some/path"}
        )
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("params"))

    def test_headers_accepts_null(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "GET", "path": "/some/path", "headers": None}
        )
        self.assertTrue(serializer.is_valid())

    def test_data_accepts_null(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "GET", "path": "/some/path", "data": None}
        )
        self.assertTrue(serializer.is_valid())

    def test_data_accepts_list(self):
        serializer = PaymentGatewayProxySerializer(
            data={"method": "POST", "path": "/some/path", "data": [1, 2, 3]}
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["data"], [1, 2, 3])

    def test_empty_payload_fails(self):
        serializer = PaymentGatewayProxySerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn("method", serializer.errors)
        self.assertIn("path", serializer.errors)
