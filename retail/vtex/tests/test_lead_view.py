from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from retail.vtex.views import LeadView


def _jwt_auth_bypass():
    """Patches JWTModuleAuthentication so requests pass without a real JWT."""

    def side_effect(request):
        request.project_uuid = str(uuid4())
        request.vtex_account = "teststore"
        request.jwt_payload = {}
        return (None, None)

    return patch(
        "retail.internal.jwt_authenticators.JWTModuleAuthentication.authenticate",
        side_effect=side_effect,
    )


class TestLeadView(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = LeadView.as_view()
        self.valid_payload = {
            "user": "user@example.com",
            "plan": "PRO",
            "vtex_account": "teststore",
            "data": {
                "carts_triggered": 154,
                "carts_converted": 42,
                "total_conversations": 820,
                "csat": "92%",
                "resolution_rate": "87%",
            },
        }

    @_jwt_auth_bypass()
    @patch("retail.vtex.views.task_notify_lead")
    @patch("retail.vtex.views.RegisterLeadUseCase")
    def test_returns_200_and_triggers_notification(self, mock_cls, mock_task, _auth):
        lead = MagicMock()
        lead.uuid = uuid4()
        lead.vtex_account = "teststore"
        lead.plan = "PRO"
        lead.region = "pt-BR"
        mock_cls.return_value.execute.return_value = lead

        request = self.factory.post("/vtex/lead/", self.valid_payload, format="json")
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["vtex_account"], "teststore")
        self.assertEqual(response.data["plan"], "PRO")
        self.assertEqual(response.data["region"], "pt-BR")
        mock_task.delay.assert_called_once_with(str(lead.uuid))

    @_jwt_auth_bypass()
    @patch("retail.vtex.views.task_notify_lead")
    @patch("retail.vtex.views.RegisterLeadUseCase")
    def test_passes_correct_dto(self, mock_cls, mock_task, _auth):
        lead = MagicMock(uuid=uuid4(), vtex_account="teststore", plan="PRO", region="")
        mock_cls.return_value.execute.return_value = lead

        request = self.factory.post("/vtex/lead/", self.valid_payload, format="json")
        self.view(request)

        dto = mock_cls.return_value.execute.call_args[0][0]
        self.assertEqual(dto.user_email, "user@example.com")
        self.assertEqual(dto.plan, "PRO")
        self.assertEqual(dto.vtex_account, "teststore")
        self.assertEqual(dto.data["carts_triggered"], 154)

    @_jwt_auth_bypass()
    def test_returns_400_when_user_missing(self, _auth):
        payload = {"plan": "PRO", "vtex_account": "teststore"}
        request = self.factory.post("/vtex/lead/", payload, format="json")
        response = self.view(request)

        self.assertEqual(response.status_code, 400)

    @_jwt_auth_bypass()
    def test_returns_400_when_plan_missing(self, _auth):
        payload = {"user": "user@example.com", "vtex_account": "teststore"}
        request = self.factory.post("/vtex/lead/", payload, format="json")
        response = self.view(request)

        self.assertEqual(response.status_code, 400)

    @_jwt_auth_bypass()
    def test_returns_400_when_vtex_account_missing(self, _auth):
        payload = {"user": "user@example.com", "plan": "PRO"}
        request = self.factory.post("/vtex/lead/", payload, format="json")
        response = self.view(request)

        self.assertEqual(response.status_code, 400)

    @_jwt_auth_bypass()
    def test_returns_400_for_invalid_email(self, _auth):
        payload = {
            "user": "not-an-email",
            "plan": "PRO",
            "vtex_account": "teststore",
        }
        request = self.factory.post("/vtex/lead/", payload, format="json")
        response = self.view(request)

        self.assertEqual(response.status_code, 400)

    @_jwt_auth_bypass()
    @patch("retail.vtex.views.task_notify_lead")
    @patch("retail.vtex.views.RegisterLeadUseCase")
    def test_data_field_is_optional(self, mock_cls, mock_task, _auth):
        lead = MagicMock(uuid=uuid4(), vtex_account="teststore", plan="PRO", region="")
        mock_cls.return_value.execute.return_value = lead

        payload = {
            "user": "user@example.com",
            "plan": "PRO",
            "vtex_account": "teststore",
        }
        request = self.factory.post("/vtex/lead/", payload, format="json")
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        dto = mock_cls.return_value.execute.call_args[0][0]
        self.assertEqual(dto.data, {})

    def test_returns_401_without_auth(self):
        request = self.factory.post("/vtex/lead/", self.valid_payload, format="json")
        response = self.view(request)

        self.assertIn(response.status_code, [401, 403])
