from django.test import TestCase

from retail.api.onboard.serializers import ActivateWebchatSerializer


class TestActivateWebchatSerializer(TestCase):
    def test_valid_data(self):
        data = {"app_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
        serializer = ActivateWebchatSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_missing_app_uuid(self):
        serializer = ActivateWebchatSerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn("app_uuid", serializer.errors)

    def test_invalid_app_uuid_format(self):
        data = {"app_uuid": "not-a-valid-uuid"}
        serializer = ActivateWebchatSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("app_uuid", serializer.errors)

    def test_tenant_and_account_id_are_ignored_from_body(self):
        data = {
            "app_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "account_id": "b1165658e9e54790881952eb99341e51",
            "vtex_account": "mystore",
        }
        serializer = ActivateWebchatSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertNotIn("account_id", serializer.validated_data)
        self.assertNotIn("vtex_account", serializer.validated_data)
