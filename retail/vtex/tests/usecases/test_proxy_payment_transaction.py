from unittest.mock import MagicMock

from django.test import TestCase

from retail.vtex.dtos.proxy_payment_transaction_dto import ProxyPaymentTransactionDTO
from retail.vtex.usecases.proxy_payment_transaction import (
    ProxyPaymentTransactionUseCase,
)


class TestProxyPaymentTransactionUseCase(TestCase):
    def setUp(self):
        self.mock_service = MagicMock()
        self.mock_resolver = MagicMock()
        self.usecase = ProxyPaymentTransactionUseCase(
            vtex_io_service=self.mock_service,
            context_resolver=self.mock_resolver,
        )
        self.dto = ProxyPaymentTransactionDTO(
            transaction_id="ABC123",
            payments=({"paymentSystem": "2", "value": 1000},),
        )

    def test_execute_calls_service_with_correct_params(self):
        self.mock_resolver.execute.return_value = ("teststore", "teststore.myvtex.com")
        self.mock_service.proxy_payment_transaction.return_value = {"ok": True}

        result = self.usecase.execute(dto=self.dto, project_uuid="test-uuid")

        self.mock_resolver.execute.assert_called_once_with(
            "test-uuid", merchant_name=None
        )
        self.mock_service.proxy_payment_transaction.assert_called_once_with(
            account_domain="teststore.myvtex.com",
            vtex_account="teststore",
            transaction_id="ABC123",
            payments=[{"paymentSystem": "2", "value": 1000}],
        )
        self.assertEqual(result, {"ok": True})

    def test_execute_uses_merchant_account_for_jwt_and_host(self):
        self.mock_resolver.execute.return_value = (
            "otherstore",
            "otherstore.myvtex.com",
        )
        self.mock_service.proxy_payment_transaction.return_value = {"ok": True}

        dto = ProxyPaymentTransactionDTO(
            transaction_id="ABC123",
            payments=({"paymentSystem": "2", "value": 1000},),
            merchant_name="otherstore",
        )
        result = self.usecase.execute(dto=dto, project_uuid="test-uuid")

        self.mock_resolver.execute.assert_called_once_with(
            "test-uuid", merchant_name="otherstore"
        )
        self.mock_service.proxy_payment_transaction.assert_called_once_with(
            account_domain="otherstore.myvtex.com",
            vtex_account="otherstore",
            transaction_id="ABC123",
            payments=[{"paymentSystem": "2", "value": 1000}],
        )
        self.assertEqual(result, {"ok": True})

    def test_defaults_context_resolver_from_service(self):
        from retail.vtex.usecases.resolve_proxy_context import (
            ResolveProxyContextUseCase,
        )

        usecase = ProxyPaymentTransactionUseCase(vtex_io_service=MagicMock())
        self.assertIsInstance(usecase.context_resolver, ResolveProxyContextUseCase)
