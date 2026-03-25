from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from retail.api.vtex_projects.views import AgentActiveView


def _jwt_auth_bypass(vtex_account: str):
    """Patches JWTModuleAuthentication so the request carries vtex_account without a real JWT token."""

    def side_effect(request):
        request.project_uuid = None
        request.vtex_account = vtex_account
        request.jwt_payload = {"vtex_account": vtex_account}
        return (None, None)

    return patch(
        "retail.internal.jwt_authenticators.JWTModuleAuthentication.authenticate",
        side_effect=side_effect,
    )


class AgentActiveViewTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = AgentActiveView.as_view()
        self.vtex_account = "teststore"

    @_jwt_auth_bypass("teststore")
    @patch("retail.api.vtex_projects.views.CheckAgentActiveUseCase")
    def test_returns_is_active_true(self, mock_use_case_cls, _auth):
        mock_use_case_cls.return_value.execute.return_value = True

        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/agent-active/",
            {"agent": "abandoned_cart"},
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_active"])

    @_jwt_auth_bypass("teststore")
    @patch("retail.api.vtex_projects.views.CheckAgentActiveUseCase")
    def test_returns_is_active_false(self, mock_use_case_cls, _auth):
        mock_use_case_cls.return_value.execute.return_value = False

        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/agent-active/",
            {"agent": "order_status"},
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

    @_jwt_auth_bypass("teststore")
    def test_returns_false_when_agent_param_missing(self, _auth):
        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/agent-active/",
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

    @_jwt_auth_bypass("teststore")
    def test_returns_false_when_agent_param_invalid(self, _auth):
        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/agent-active/",
            {"agent": "invalid_type"},
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

    @_jwt_auth_bypass("teststore")
    @patch("retail.api.vtex_projects.views.CheckAgentActiveUseCase")
    def test_returns_false_on_use_case_exception(self, mock_use_case_cls, _auth):
        mock_use_case_cls.return_value.execute.side_effect = Exception("db error")

        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/agent-active/",
            {"agent": "abandoned_cart"},
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

    def test_returns_auth_error_without_token(self):
        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/agent-active/",
            {"agent": "abandoned_cart"},
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertIn(response.status_code, [401, 403])

    @_jwt_auth_bypass("teststore")
    @patch("retail.api.vtex_projects.views.CheckAgentActiveUseCase")
    def test_passes_correct_params_to_use_case(self, mock_use_case_cls, _auth):
        mock_use_case_cls.return_value.execute.return_value = True

        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/agent-active/",
            {"agent": "order_status"},
        )
        self.view(request, vtex_account=self.vtex_account)

        mock_use_case_cls.return_value.execute.assert_called_once_with(
            vtex_account=self.vtex_account,
            agent_type="order_status",
        )
