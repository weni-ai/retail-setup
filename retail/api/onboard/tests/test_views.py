from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from retail.api.onboard.views import ActivateWebchatView


class TestActivateWebchatView(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.valid_payload = {
            "app_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "account_id": "b1165658e9e54790881952eb99341e51",
        }

    def _post(self, data):
        request = self.factory.post(
            "/api/onboard/wwc/activate/",
            data=data,
            format="json",
        )
        request.user = MagicMock(is_authenticated=True)
        return request

    @patch("retail.api.onboard.views.WebchatPushService")
    @patch("retail.api.onboard.views.IntegrationsService")
    @patch("retail.api.onboard.views.PublishWebchatScriptUseCase")
    def test_success_returns_201(
        self, MockUseCase, MockIntegrationsService, MockPushService
    ):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "script_url": "https://bucket.s3.amazonaws.com/webchat.js"
        }
        MockUseCase.return_value.execute.return_value = mock_result

        request = self._post(self.valid_payload)

        with patch.object(ActivateWebchatView, "authentication_classes", []):
            with patch.object(ActivateWebchatView, "permission_classes", []):
                response = ActivateWebchatView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["script_url"],
            "https://bucket.s3.amazonaws.com/webchat.js",
        )

    def test_missing_app_uuid_returns_400(self):
        request = self._post({"account_id": self.valid_payload["account_id"]})

        with patch.object(ActivateWebchatView, "authentication_classes", []):
            with patch.object(ActivateWebchatView, "permission_classes", []):
                response = ActivateWebchatView.as_view()(request)

        self.assertEqual(response.status_code, 400)

    def test_missing_account_id_returns_400(self):
        request = self._post({"app_uuid": self.valid_payload["app_uuid"]})

        with patch.object(ActivateWebchatView, "authentication_classes", []):
            with patch.object(ActivateWebchatView, "permission_classes", []):
                response = ActivateWebchatView.as_view()(request)

        self.assertEqual(response.status_code, 400)

    def test_invalid_app_uuid_format_returns_400(self):
        request = self._post(
            {"app_uuid": "not-a-uuid", "account_id": "b1165658e9e54790881952eb99341e51"}
        )

        with patch.object(ActivateWebchatView, "authentication_classes", []):
            with patch.object(ActivateWebchatView, "permission_classes", []):
                response = ActivateWebchatView.as_view()(request)

        self.assertEqual(response.status_code, 400)
