from django.test import TestCase

from retail.vtex.serializers import VtexProxySerializer


class TestVtexProxySerializer(TestCase):
    def test_valid_minimal_payload(self):
        serializer = VtexProxySerializer(
            data={"method": "GET", "path": "/api/oms/pvt/orders"}
        )
        self.assertTrue(serializer.is_valid())

    def test_merchant_name_is_optional(self):
        serializer = VtexProxySerializer(
            data={"method": "GET", "path": "/api/oms/pvt/orders"}
        )
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("merchant_name"))

    def test_accepts_merchant_name(self):
        serializer = VtexProxySerializer(
            data={
                "method": "GET",
                "path": "/api/oms/pvt/orders",
                "merchant_name": "otherstore",
            }
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["merchant_name"], "otherstore")

    def test_merchant_name_accepts_null(self):
        serializer = VtexProxySerializer(
            data={
                "method": "GET",
                "path": "/api/oms/pvt/orders",
                "merchant_name": None,
            }
        )
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("merchant_name"))

    def test_method_is_required(self):
        serializer = VtexProxySerializer(data={"path": "/some/path"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("method", serializer.errors)

    def test_path_is_required(self):
        serializer = VtexProxySerializer(data={"method": "GET"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("path", serializer.errors)
