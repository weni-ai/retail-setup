from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from retail.api.vtex_projects.views import AgentActiveView, OnboardingCompleteView
from retail.api.vtex_projects.usecases.check_onboarding_complete import (
    OnboardingStatus,
)
from retail.internal.test_mixins import patch_retail_auth


def _jwt_auth_bypass(vtex_account: str):
    """Patch unified retail auth (JWT/Keycloak) for agent-active checks."""

    return patch_retail_auth(vtex_account=vtex_account)


class AgentActiveViewTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = AgentActiveView.as_view()
        self.vtex_account = "teststore"

    @_jwt_auth_bypass("teststore")
    @patch("retail.api.vtex_projects.views.CheckAgentActiveUseCase")
    def test_returns_is_active_true(self, mock_use_case_cls, _auth):
        mock_use_case_cls.return_value.execute_any.return_value = True

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
        mock_use_case_cls.return_value.execute_any.return_value = False

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
        mock_use_case_cls.return_value.execute_any.side_effect = Exception("db error")

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
        mock_use_case_cls.return_value.execute_any.return_value = True

        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/agent-active/",
            {"agent": "order_status"},
        )
        self.view(request, vtex_account=self.vtex_account)

        mock_use_case_cls.return_value.execute_any.assert_called_once_with(
            vtex_account=self.vtex_account,
            agent_types=["order_status"],
        )

    @_jwt_auth_bypass("teststore")
    @patch("retail.api.vtex_projects.views.CheckAgentActiveUseCase")
    def test_accepts_payment_recovery_agent_type(self, mock_use_case_cls, _auth):
        mock_use_case_cls.return_value.execute_any.return_value = True

        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/agent-active/",
            {"agent": "payment_recovery"},
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_active"])
        mock_use_case_cls.return_value.execute_any.assert_called_once_with(
            vtex_account=self.vtex_account,
            agent_types=["payment_recovery"],
        )

    @_jwt_auth_bypass("teststore")
    @patch("retail.api.vtex_projects.views.CheckAgentActiveUseCase")
    def test_accepts_repeated_agent_param_with_or_semantics(
        self, mock_use_case_cls, _auth
    ):
        mock_use_case_cls.return_value.execute_any.return_value = True

        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/agent-active/"
            "?agent=order_status&agent=payment_recovery",
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_active"])
        mock_use_case_cls.return_value.execute_any.assert_called_once_with(
            vtex_account=self.vtex_account,
            agent_types=["order_status", "payment_recovery"],
        )

    @_jwt_auth_bypass("teststore")
    @patch("retail.api.vtex_projects.views.CheckAgentActiveUseCase")
    def test_rejects_repeated_agent_when_any_value_is_invalid(
        self, mock_use_case_cls, _auth
    ):
        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/agent-active/"
            "?agent=order_status&agent=invalid_type",
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])
        mock_use_case_cls.return_value.execute_any.assert_not_called()


class OnboardingCompleteViewTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = OnboardingCompleteView.as_view()
        self.vtex_account = "teststore"

    @patch_retail_auth(vtex_account="teststore")
    @patch("retail.api.vtex_projects.views.CheckOnboardingCompleteUseCase")
    def test_returns_complete_with_null_account_id(self, mock_use_case_cls, _auth):
        mock_use_case_cls.return_value.execute.return_value = OnboardingStatus(
            is_complete=True, account_id=None
        )

        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/onboarding-complete/"
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_complete"])
        self.assertIsNone(response.data["accountId"])

    @patch_retail_auth(vtex_account="teststore")
    @patch("retail.api.vtex_projects.views.CheckOnboardingCompleteUseCase")
    def test_returns_incomplete(self, mock_use_case_cls, _auth):
        mock_use_case_cls.return_value.execute.return_value = OnboardingStatus(
            is_complete=False, account_id=None
        )

        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/onboarding-complete/"
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_complete"])
        self.assertIsNone(response.data["accountId"])

    @patch_retail_auth(vtex_account="teststore")
    @patch("retail.api.vtex_projects.views.CheckOnboardingCompleteUseCase")
    def test_returns_safe_default_on_exception(self, mock_use_case_cls, _auth):
        mock_use_case_cls.return_value.execute.side_effect = Exception("db error")

        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/onboarding-complete/"
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_complete"])
        self.assertIsNone(response.data["accountId"])

    def test_returns_auth_error_without_token(self):
        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/onboarding-complete/"
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertIn(response.status_code, [401, 403])

    @patch_retail_auth(vtex_account=None)
    def test_missing_tenant_returns_403(self, _auth):
        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/onboarding-complete/"
        )
        response = self.view(request, vtex_account=self.vtex_account)

        self.assertEqual(response.status_code, 403)

    @patch_retail_auth(vtex_account="teststore")
    @patch("retail.api.vtex_projects.views.CheckOnboardingCompleteUseCase")
    def test_passes_correct_vtex_account_to_use_case(self, mock_use_case_cls, _auth):
        mock_use_case_cls.return_value.execute.return_value = OnboardingStatus(
            is_complete=False, account_id=None
        )

        request = self.factory.get(
            f"/api/vtex-projects/{self.vtex_account}/onboarding-complete/"
        )
        self.view(request, vtex_account=self.vtex_account)

        mock_use_case_cls.return_value.execute.assert_called_once_with(
            vtex_account=self.vtex_account,
        )
