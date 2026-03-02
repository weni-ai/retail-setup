from django.test import TestCase

from retail.api.onboard.serializers import ActivateWebchatSerializer


class TestActivateWebchatSerializer(TestCase):
    def test_valid_data(self):
        data = {
            "app_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "account_id": "b1165658e9e54790881952eb99341e51",
        }
        serializer = ActivateWebchatSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_missing_app_uuid(self):
        data = {"account_id": "b1165658e9e54790881952eb99341e51"}
        serializer = ActivateWebchatSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("app_uuid", serializer.errors)

    def test_missing_account_id(self):
        data = {"app_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
        serializer = ActivateWebchatSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("account_id", serializer.errors)

    def test_invalid_app_uuid_format(self):
        data = {
            "app_uuid": "not-a-valid-uuid",
            "account_id": "b1165658e9e54790881952eb99341e51",
        }
        serializer = ActivateWebchatSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("app_uuid", serializer.errors)

    def test_account_id_accepts_hex_string(self):
        data = {
            "app_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "account_id": "b1165658e9e54790881952eb99341e51",
        }
        serializer = ActivateWebchatSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(
            serializer.validated_data["account_id"],
            "b1165658e9e54790881952eb99341e51",
        )

    def test_empty_payload(self):
        serializer = ActivateWebchatSerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn("app_uuid", serializer.errors)
        self.assertIn("account_id", serializer.errors)
