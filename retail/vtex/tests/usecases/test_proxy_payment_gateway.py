from unittest.mock import MagicMock, patch

from django.test import TestCase

from retail.vtex.dtos.proxy_payment_gateway_dto import ProxyPaymentGatewayDTO
from retail.vtex.usecases.proxy_payment_gateway import ProxyPaymentGatewayUseCase


class TestProxyPaymentGatewayUseCase(TestCase):
    def setUp(self):
        self.mock_service = MagicMock()
        self.usecase = ProxyPaymentGatewayUseCase(vtex_io_service=self.mock_service)
        self.dto = ProxyPaymentGatewayDTO(
            method="GET",
            path="/api/pvt/transactions/ABC123/interactions",
        )

    @patch.object(ProxyPaymentGatewayUseCase, "_get_vtex_context")
    def test_execute_calls_service_with_correct_params(self, mock_context):
        mock_context.return_value = ("teststore", "teststore.myvtex.com")
        self.mock_service.proxy_payment_gateway.return_value = {"data": []}

        result = self.usecase.execute(dto=self.dto, project_uuid="test-uuid")

        self.mock_service.proxy_payment_gateway.assert_called_once_with(
            account_domain="teststore.myvtex.com",
            vtex_account="teststore",
            method="GET",
            path="/api/pvt/transactions/ABC123/interactions",
            headers=None,
            data=None,
            params=None,
        )
        self.assertEqual(result, {"data": []})

    @patch.object(ProxyPaymentGatewayUseCase, "_get_vtex_context")
    def test_execute_forwards_optional_fields(self, mock_context):
        mock_context.return_value = ("teststore", "teststore.myvtex.com")
        self.mock_service.proxy_payment_gateway.return_value = {}

        dto = ProxyPaymentGatewayDTO(
            method="POST",
            path="/api/pvt/transactions/ABC123/payments",
            headers={"X-Custom": "value"},
            data={"key": "value"},
            params={"an": "teststore"},
        )
        self.usecase.execute(dto=dto, project_uuid="test-uuid")

        call_kwargs = self.mock_service.proxy_payment_gateway.call_args[1]
        self.assertEqual(call_kwargs["headers"], {"X-Custom": "value"})
        self.assertEqual(call_kwargs["data"], {"key": "value"})
        self.assertEqual(call_kwargs["params"], {"an": "teststore"})

    @patch.object(ProxyPaymentGatewayUseCase, "_get_vtex_context")
    def test_execute_raises_when_project_not_found(self, mock_context):
        mock_context.side_effect = ValueError("Project not found for given UUID.")

        with self.assertRaises(ValueError) as ctx:
            self.usecase.execute(dto=self.dto, project_uuid="invalid-uuid")

        self.assertIn("Project not found", str(ctx.exception))

    @patch.object(ProxyPaymentGatewayUseCase, "_get_vtex_context")
    def test_execute_raises_when_vtex_account_missing(self, mock_context):
        mock_context.side_effect = ValueError("VTEX account not defined for project.")

        with self.assertRaises(ValueError):
            self.usecase.execute(dto=self.dto, project_uuid="test-uuid")

    @patch.object(ProxyPaymentGatewayUseCase, "_get_vtex_context")
    def test_execute_returns_service_response(self, mock_context):
        mock_context.return_value = ("teststore", "teststore.myvtex.com")
        expected = {
            "status": 200,
            "data": [{"transactionId": "ABC123", "payments": []}],
        }
        self.mock_service.proxy_payment_gateway.return_value = expected

        result = self.usecase.execute(dto=self.dto, project_uuid="test-uuid")

        self.assertEqual(result, expected)
