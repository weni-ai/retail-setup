from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from retail.vtex.views import PaymentGatewayProxyView


def _jwt_auth_bypass(project_uuid: str):
    """
    Patches JWTModuleAuthentication so the request carries
    project_uuid without a real JWT token.
    """

    def side_effect(request):
        request.project_uuid = project_uuid
        request.vtex_account = None
        request.jwt_payload = {"project_uuid": project_uuid}
        return (None, None)

    return patch(
        "retail.internal.jwt_authenticators.JWTModuleAuthentication.authenticate",
        side_effect=side_effect,
    )


class TestPaymentGatewayProxyView(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = PaymentGatewayProxyView.as_view()
        self.url = "/vtex/payments/gateway-proxy/"
        self.valid_payload = {
            "method": "GET",
            "path": "/api/pvt/transactions/ABC123/interactions",
        }

    @_jwt_auth_bypass("test-uuid")
    @patch("retail.vtex.views.ProxyPaymentGatewayUseCase")
    def test_returns_200_with_upstream_response(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = {
            "transactions": [{"id": "ABC123"}]
        }

        request = self.factory.post(self.url, self.valid_payload, format="json")
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["transactions"][0]["id"], "ABC123")

    @_jwt_auth_bypass("test-uuid")
    @patch("retail.vtex.views.ProxyPaymentGatewayUseCase")
    def test_passes_correct_dto(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = {}

        payload = {
            "method": "POST",
            "path": "/api/pvt/transactions/ABC123/payments",
            "headers": {"X-Custom": "value"},
            "data": {"key": "value"},
            "params": {"an": "teststore"},
        }
        request = self.factory.post(self.url, payload, format="json")
        self.view(request)

        call_kwargs = mock_cls.return_value.execute.call_args[1]
        dto = call_kwargs["dto"]
        self.assertEqual(dto.method, "POST")
        self.assertEqual(dto.path, "/api/pvt/transactions/ABC123/payments")
        self.assertEqual(dto.headers, {"X-Custom": "value"})
        self.assertEqual(dto.data, {"key": "value"})
        self.assertEqual(dto.params, {"an": "teststore"})
        self.assertEqual(call_kwargs["project_uuid"], "test-uuid")

    @_jwt_auth_bypass("test-uuid")
    def test_returns_400_when_method_missing(self, _auth):
        request = self.factory.post(
            self.url,
            {"path": "/api/pvt/transactions/ABC123"},
            format="json",
        )
        response = self.view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("method", response.data)

    @_jwt_auth_bypass("test-uuid")
    def test_returns_400_when_path_missing(self, _auth):
        request = self.factory.post(
            self.url,
            {"method": "GET"},
            format="json",
        )
        response = self.view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("path", response.data)

    @_jwt_auth_bypass("test-uuid")
    def test_returns_400_for_unsupported_method_patch(self, _auth):
        request = self.factory.post(
            self.url,
            {"method": "PATCH", "path": "/api/pvt/transactions/ABC123"},
            format="json",
        )
        response = self.view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("method", response.data)

    @_jwt_auth_bypass("test-uuid")
    @patch("retail.vtex.views.ProxyPaymentGatewayUseCase")
    def test_accepts_get_post_put_methods(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = {}

        for method in ["GET", "POST", "PUT"]:
            request = self.factory.post(
                self.url,
                {"method": method, "path": "/api/pvt/transactions/ABC123"},
                format="json",
            )
            response = self.view(request)
            self.assertEqual(response.status_code, 200, f"Failed for method {method}")

    @_jwt_auth_bypass("test-uuid")
    @patch("retail.vtex.views.ProxyPaymentGatewayUseCase")
    def test_optional_fields_default_to_none(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = {}

        request = self.factory.post(self.url, self.valid_payload, format="json")
        self.view(request)

        dto = mock_cls.return_value.execute.call_args[1]["dto"]
        self.assertIsNone(dto.headers)
        self.assertIsNone(dto.data)
        self.assertIsNone(dto.params)

    def test_returns_401_without_auth(self):
        request = self.factory.post(self.url, self.valid_payload, format="json")
        response = self.view(request)

        self.assertIn(response.status_code, [401, 403])
