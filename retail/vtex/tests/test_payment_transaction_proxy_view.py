from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from retail.vtex.views import PaymentTransactionProxyView


def _jwt_auth_bypass(project_uuid: str):
    def side_effect(request):
        request.project_uuid = project_uuid
        request.vtex_account = None
        request.jwt_payload = {"project_uuid": project_uuid}
        return (None, None)

    return patch(
        "retail.internal.jwt_authenticators.JWTModuleAuthentication.authenticate",
        side_effect=side_effect,
    )


class TestPaymentTransactionProxyView(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = PaymentTransactionProxyView.as_view()
        self.url = "/vtex/payments/send-transaction/"
        self.valid_payload = {
            "transaction_id": "ABC123",
            "payments": [{"paymentSystem": "2", "value": 1000}],
        }

    @_jwt_auth_bypass("test-uuid")
    @patch("retail.vtex.views.ProxyPaymentTransactionUseCase")
    def test_passes_merchant_name_on_dto(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = {}

        payload = {**self.valid_payload, "merchant_name": "otherstore"}
        request = self.factory.post(self.url, payload, format="json")
        self.view(request)

        call_kwargs = mock_cls.return_value.execute.call_args[1]
        dto = call_kwargs["dto"]
        self.assertEqual(dto.transaction_id, "ABC123")
        self.assertEqual(dto.payments, ({"paymentSystem": "2", "value": 1000},))
        self.assertEqual(dto.merchant_name, "otherstore")
        self.assertEqual(call_kwargs["project_uuid"], "test-uuid")

    @_jwt_auth_bypass("test-uuid")
    @patch("retail.vtex.views.ProxyPaymentTransactionUseCase")
    def test_merchant_name_defaults_to_none(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = {}

        request = self.factory.post(self.url, self.valid_payload, format="json")
        self.view(request)

        dto = mock_cls.return_value.execute.call_args[1]["dto"]
        self.assertIsNone(dto.merchant_name)
