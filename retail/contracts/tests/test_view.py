from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from retail.contracts.exceptions import (
    ContractTemplateNotFoundError,
    ProjectNotFoundError,
)
from retail.internal.test_mixins import patch_retail_auth


def _auth_bypass():
    """Patches unified retail auth with a tenant-scoped JWT context."""

    return patch_retail_auth(
        vtex_account="teststore",
        user_email="user@example.com",
    )


class RegisterContractAcceptanceViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v3/contracts/accept/"
        self.valid_payload = {
            "user_id": str(uuid4()),
            "email_at_acceptance": "merchant@store.com",
            "user_name": "Carlos Eduardo Ferreira",
            "vtex_account": "teststore",
            "plan": "Growth",
            "acceptance_method": "checkbox",
            "checkbox_label_text": "I accept the terms.",
        }

    def _acceptance_stub(self):
        return SimpleNamespace(
            uuid=uuid4(),
            accepted_at=timezone.now(),
            contract_document_key="contratos/teststore/x.pdf",
        )

    @_auth_bypass()
    @patch("retail.contracts.views.RegisterContractAcceptanceUseCase")
    def test_returns_201_with_receipt(self, mock_cls, _auth):
        acceptance = self._acceptance_stub()
        mock_cls.return_value.execute.return_value = acceptance

        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["acceptance_id"], str(acceptance.uuid))
        self.assertEqual(
            response.data["contract_document_key"],
            "contratos/teststore/x.pdf",
        )

    @_auth_bypass()
    @patch("retail.contracts.views.RegisterContractAcceptanceUseCase")
    def test_passes_subscriber_email_from_body(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = self._acceptance_stub()

        self.client.post(
            self.url,
            self.valid_payload,
            format="json",
            HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1",
            HTTP_USER_AGENT="Mozilla/5.0",
            HTTP_X_SESSION_ID="session-xyz",
            HTTP_X_REQUEST_ID="11111111-1111-1111-1111-111111111111",
        )

        dto = mock_cls.return_value.execute.call_args[0][0]
        self.assertEqual(dto.ip_address, "203.0.113.7")
        self.assertEqual(dto.user_agent, "Mozilla/5.0")
        self.assertEqual(dto.session_id, "session-xyz")
        self.assertEqual(dto.request_id, "11111111-1111-1111-1111-111111111111")
        self.assertEqual(dto.email_at_acceptance, "merchant@store.com")
        self.assertEqual(dto.vtex_account, "teststore")
        self.assertIsNone(dto.geo_country)

    @_auth_bypass()
    @patch("retail.contracts.views.RegisterContractAcceptanceUseCase")
    def test_invalid_request_id_header_becomes_none(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = self._acceptance_stub()

        self.client.post(
            self.url,
            self.valid_payload,
            format="json",
            HTTP_X_REQUEST_ID="not-a-uuid",
        )

        dto = mock_cls.return_value.execute.call_args[0][0]
        self.assertIsNone(dto.request_id)

    @_auth_bypass()
    def test_returns_400_when_field_missing(self, _auth):
        payload = dict(self.valid_payload)
        payload.pop("checkbox_label_text")

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("checkbox_label_text", response.data)

    @_auth_bypass()
    def test_returns_400_when_email_missing(self, _auth):
        payload = dict(self.valid_payload)
        payload.pop("email_at_acceptance")

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("email_at_acceptance", response.data)

    @_auth_bypass()
    def test_returns_400_when_plan_missing(self, _auth):
        payload = dict(self.valid_payload)
        payload.pop("plan")

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("plan", response.data)

    @_auth_bypass()
    @patch("retail.contracts.views.RegisterContractAcceptanceUseCase")
    def test_returns_404_when_domain_error(self, mock_cls, _auth):
        mock_cls.return_value.execute.side_effect = ProjectNotFoundError("missing")

        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, 404)

    @_auth_bypass()
    @patch("retail.contracts.views.RegisterContractAcceptanceUseCase")
    def test_returns_404_when_template_not_found(self, mock_cls, _auth):
        mock_cls.return_value.execute.side_effect = ContractTemplateNotFoundError(
            "Active contract template not found"
        )

        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, 404)

    @_auth_bypass()
    @patch("retail.contracts.views.RegisterContractAcceptanceUseCase")
    def test_falls_back_to_remote_addr_without_forwarded_for(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = self._acceptance_stub()

        self.client.post(
            self.url,
            self.valid_payload,
            format="json",
            REMOTE_ADDR="198.51.100.42",
        )

        dto = mock_cls.return_value.execute.call_args[0][0]
        self.assertEqual(dto.ip_address, "198.51.100.42")

    @_auth_bypass()
    @patch("retail.contracts.views.RegisterContractAcceptanceUseCase")
    def test_session_id_is_empty_without_header_or_session(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = self._acceptance_stub()

        self.client.post(self.url, self.valid_payload, format="json")

        dto = mock_cls.return_value.execute.call_args[0][0]
        self.assertEqual(dto.session_id, "")

    def test_returns_403_without_auth(self):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, 403)
