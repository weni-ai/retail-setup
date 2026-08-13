from unittest.mock import MagicMock, patch

from django.test import TestCase

from retail.vtex.dtos.proxy_payment_transaction_dto import ProxyPaymentTransactionDTO
from retail.vtex.usecases.proxy_payment_transaction import (
    ProxyPaymentTransactionUseCase,
)


class TestProxyPaymentTransactionUseCase(TestCase):
    def setUp(self):
        self.mock_service = MagicMock()
        self.usecase = ProxyPaymentTransactionUseCase(vtex_io_service=self.mock_service)
        self.dto = ProxyPaymentTransactionDTO(
            transaction_id="ABC123",
            payments=({"paymentSystem": "2", "value": 1000},),
        )

    @patch.object(ProxyPaymentTransactionUseCase, "_get_vtex_context")
    def test_execute_calls_service_with_correct_params(self, mock_context):
        mock_context.return_value = ("teststore", "teststore.myvtex.com")
        self.mock_service.proxy_payment_transaction.return_value = {"ok": True}

        result = self.usecase.execute(dto=self.dto, project_uuid="test-uuid")

        mock_context.assert_called_once_with("test-uuid", merchant_name=None)
        self.mock_service.proxy_payment_transaction.assert_called_once_with(
            account_domain="teststore.myvtex.com",
            vtex_account="teststore",
            transaction_id="ABC123",
            payments=[{"paymentSystem": "2", "value": 1000}],
        )
        self.assertEqual(result, {"ok": True})

    @patch.object(ProxyPaymentTransactionUseCase, "_get_vtex_context")
    def test_execute_passes_merchant_name_to_context(self, mock_context):
        mock_context.return_value = ("teststore", "otherstore.myvtex.com")
        self.mock_service.proxy_payment_transaction.return_value = {"ok": True}

        dto = ProxyPaymentTransactionDTO(
            transaction_id="ABC123",
            payments=({"paymentSystem": "2", "value": 1000},),
            merchant_name="otherstore",
        )
        result = self.usecase.execute(dto=dto, project_uuid="test-uuid")

        mock_context.assert_called_once_with("test-uuid", merchant_name="otherstore")
        self.mock_service.proxy_payment_transaction.assert_called_once_with(
            account_domain="otherstore.myvtex.com",
            vtex_account="teststore",
            transaction_id="ABC123",
            payments=[{"paymentSystem": "2", "value": 1000}],
        )
        self.assertEqual(result, {"ok": True})
