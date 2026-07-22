from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from retail.api.onboard.views import ActivateWebchatView, ActivateWppCloudView
from retail.internal.permissions import PermissionsLevels
from retail.internal.test_mixins import patch_retail_auth
from retail.projects.models import Project

CONNECT_PROXY_PATH = "retail.internal.permissions.ConnectServiceProxy"

CACHE_OVERRIDE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "activate-webchat-tests",
    }
}


@override_settings(CACHES=CACHE_OVERRIDE)
class TestActivateWebchatView(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = ActivateWebchatView.as_view()
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.account_id = "b1165658e9e54790881952eb99341e51"
        self.valid_payload = {
            "app_uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        }

    def _post(self, data):
        request = self.factory.post(
            "/api/onboard/wwc/activate/",
            data=data,
            format="json",
        )
        return self.view(request)

    @staticmethod
    def _grant(MockProxy, level=PermissionsLevels.contributor):
        MockProxy.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": level},
        )

    @patch_retail_auth(
        vtex_account="mystore",
        user_email="user@weni.ai",
        account_id="b1165658e9e54790881952eb99341e51",
    )
    @patch(CONNECT_PROXY_PATH)
    @patch("retail.api.onboard.views.WebchatPushService")
    @patch("retail.api.onboard.views.IntegrationsService")
    @patch("retail.api.onboard.views.PublishWebchatScriptUseCase")
    def test_success_returns_201(
        self, MockUseCase, MockIntegrationsService, MockPushService, MockProxy, _auth
    ):
        self._grant(MockProxy)
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "script_urls": ["https://bucket.s3.amazonaws.com/webchat.js"]
        }
        MockUseCase.return_value.execute.return_value = mock_result

        response = self._post(self.valid_payload)

        self.assertEqual(response.status_code, 201)
        MockUseCase.return_value.execute.assert_called_once()
        dto = MockUseCase.return_value.execute.call_args.args[0]
        self.assertEqual(dto.vtex_account, "mystore")
        self.assertEqual(dto.account_id, self.account_id)

    @patch_retail_auth(
        vtex_account="mystore",
        user_email="user@weni.ai",
        account_id="b1165658e9e54790881952eb99341e51",
    )
    @patch(CONNECT_PROXY_PATH)
    @patch("retail.api.onboard.views.WebchatPushService")
    @patch("retail.api.onboard.views.IntegrationsService")
    @patch("retail.api.onboard.views.PublishWebchatScriptUseCase")
    def test_jwt_uses_account_id_and_vtex_account_from_token(
        self, MockUseCase, MockIntegrationsService, MockPushService, MockProxy, _auth
    ):
        self._grant(MockProxy)
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"script_urls": []}
        MockUseCase.return_value.execute.return_value = mock_result

        response = self._post(self.valid_payload)

        self.assertEqual(response.status_code, 201)
        dto = MockUseCase.return_value.execute.call_args.args[0]
        self.assertEqual(dto.vtex_account, "mystore")
        self.assertEqual(dto.account_id, self.account_id)

    @patch_retail_auth(
        vtex_account="mystore",
        is_internal=True,
        account_id="b1165658e9e54790881952eb99341e51",
    )
    @patch(CONNECT_PROXY_PATH)
    @patch("retail.api.onboard.views.WebchatPushService")
    @patch("retail.api.onboard.views.IntegrationsService")
    @patch("retail.api.onboard.views.PublishWebchatScriptUseCase")
    def test_internal_caller_bypasses_permission(
        self, MockUseCase, MockIntegrationsService, MockPushService, MockProxy, _auth
    ):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"script_urls": []}
        MockUseCase.return_value.execute.return_value = mock_result

        response = self._post(self.valid_payload)

        self.assertEqual(response.status_code, 201)
        MockProxy.return_value.get_user_permissions.assert_not_called()

    @patch_retail_auth(
        vtex_account="mystore",
        user_email="user@weni.ai",
        account_id="b1165658e9e54790881952eb99341e51",
    )
    @patch(CONNECT_PROXY_PATH)
    def test_user_without_project_access_returns_403(self, MockProxy, _auth):
        self._grant(MockProxy, level=PermissionsLevels.viewer)

        response = self._post(self.valid_payload)

        self.assertEqual(response.status_code, 403)

    @patch_retail_auth(
        vtex_account="mystore",
        user_email="user@weni.ai",
        account_id="b1165658e9e54790881952eb99341e51",
    )
    @patch(CONNECT_PROXY_PATH)
    def test_missing_app_uuid_returns_400(self, MockProxy, _auth):
        self._grant(MockProxy)

        response = self._post({})

        self.assertEqual(response.status_code, 400)

    @patch_retail_auth(vtex_account="mystore", user_email="user@weni.ai")
    @patch(CONNECT_PROXY_PATH)
    def test_missing_account_id_in_token_returns_400(self, MockProxy, _auth):
        self._grant(MockProxy)

        response = self._post(self.valid_payload)

        self.assertEqual(response.status_code, 400)

    @patch_retail_auth(
        vtex_account="mystore",
        user_email="user@weni.ai",
        account_id="b1165658e9e54790881952eb99341e51",
    )
    @patch(CONNECT_PROXY_PATH)
    def test_invalid_app_uuid_format_returns_400(self, MockProxy, _auth):
        self._grant(MockProxy)

        response = self._post({"app_uuid": "not-a-uuid"})

        self.assertEqual(response.status_code, 400)

    @patch_retail_auth(
        vtex_account=None,
        user_email="user@weni.ai",
        account_id="b1165658e9e54790881952eb99341e51",
    )
    def test_missing_tenant_returns_403(self, _auth):
        response = self._post(self.valid_payload)

        self.assertEqual(response.status_code, 403)


class TestActivateWppCloudView(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = ActivateWppCloudView.as_view()
        self.project_uuid = str(uuid4())
        self.valid_payload = {"percentage": 10}

    def _post(self, data):
        request = self.factory.post(
            "/api/onboard/wpp-cloud/activate/",
            data=data,
            format="json",
        )
        return self.view(request)

    @patch("retail.api.onboard.views.ActivateWppCloudUseCase")
    def test_success_returns_200(self, MockUseCase):
        mock_integrated = MagicMock()
        mock_integrated.uuid = uuid4()
        mock_integrated.contact_percentage = 10
        MockUseCase.return_value.execute.return_value = mock_integrated

        with patch_retail_auth(project_uuid=self.project_uuid):
            response = self._post(self.valid_payload)

        self.assertEqual(response.status_code, 200)
        dto = MockUseCase.return_value.execute.call_args.args[0]
        self.assertEqual(dto.project_uuid, self.project_uuid)

    @patch("retail.api.onboard.views.ActivateWppCloudUseCase")
    def test_jwt_uses_project_uuid_from_token(self, MockUseCase):
        mock_integrated = MagicMock()
        mock_integrated.uuid = uuid4()
        mock_integrated.contact_percentage = 10
        MockUseCase.return_value.execute.return_value = mock_integrated

        with patch_retail_auth(project_uuid=self.project_uuid):
            response = self._post({"percentage": 10})

        self.assertEqual(response.status_code, 200)
        dto = MockUseCase.return_value.execute.call_args.args[0]
        self.assertEqual(dto.project_uuid, self.project_uuid)

    def test_missing_project_uuid_returns_403(self):
        with patch_retail_auth(project_uuid=None):
            response = self._post({"percentage": 10})

        self.assertEqual(response.status_code, 403)

    def test_missing_percentage_returns_400(self):
        with patch_retail_auth(project_uuid=self.project_uuid):
            response = self._post({})

        self.assertEqual(response.status_code, 400)

    def test_percentage_above_100_returns_400(self):
        with patch_retail_auth(project_uuid=self.project_uuid):
            response = self._post({"percentage": 101})

        self.assertEqual(response.status_code, 400)

    def test_negative_percentage_returns_400(self):
        with patch_retail_auth(project_uuid=self.project_uuid):
            response = self._post({"percentage": -1})

        self.assertEqual(response.status_code, 400)
