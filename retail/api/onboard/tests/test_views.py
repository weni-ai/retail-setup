from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from retail.api.onboard.views import ActivateWebchatView, ActivateWppCloudView


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


class TestActivateWppCloudView(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.project_uuid = str(uuid4())
        self.valid_payload = {
            "project_uuid": self.project_uuid,
            "percentage": 10,
        }

    def _post(self, data):
        request = self.factory.post(
            "/api/onboard/wpp-cloud/activate/",
            data=data,
            format="json",
        )
        request.user = MagicMock(is_authenticated=True)
        return request

    @patch("retail.api.onboard.views.ActivateWppCloudUseCase")
    def test_success_returns_200(self, MockUseCase):
        mock_integrated = MagicMock()
        mock_integrated.uuid = uuid4()
        mock_integrated.contact_percentage = 10
        MockUseCase.return_value.execute.return_value = mock_integrated

        request = self._post(self.valid_payload)

        with patch.object(ActivateWppCloudView, "authentication_classes", []):
            with patch.object(ActivateWppCloudView, "permission_classes", []):
                response = ActivateWppCloudView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["contact_percentage"], 10)
        self.assertIn("integrated_agent_uuid", response.data)

    def test_missing_project_uuid_returns_400(self):
        request = self._post({"percentage": 10})

        with patch.object(ActivateWppCloudView, "authentication_classes", []):
            with patch.object(ActivateWppCloudView, "permission_classes", []):
                response = ActivateWppCloudView.as_view()(request)

        self.assertEqual(response.status_code, 400)

    def test_missing_percentage_returns_400(self):
        request = self._post({"project_uuid": self.project_uuid})

        with patch.object(ActivateWppCloudView, "authentication_classes", []):
            with patch.object(ActivateWppCloudView, "permission_classes", []):
                response = ActivateWppCloudView.as_view()(request)

        self.assertEqual(response.status_code, 400)

    def test_percentage_above_100_returns_400(self):
        request = self._post(
            {
                "project_uuid": self.project_uuid,
                "percentage": 101,
            }
        )

        with patch.object(ActivateWppCloudView, "authentication_classes", []):
            with patch.object(ActivateWppCloudView, "permission_classes", []):
                response = ActivateWppCloudView.as_view()(request)

        self.assertEqual(response.status_code, 400)

    def test_negative_percentage_returns_400(self):
        request = self._post(
            {
                "project_uuid": self.project_uuid,
                "percentage": -1,
            }
        )

        with patch.object(ActivateWppCloudView, "authentication_classes", []):
            with patch.object(ActivateWppCloudView, "permission_classes", []):
                response = ActivateWppCloudView.as_view()(request)

        self.assertEqual(response.status_code, 400)
