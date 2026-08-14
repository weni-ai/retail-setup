from unittest.mock import MagicMock

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from retail.clients.exceptions import CustomAPIException
from retail.vtex.usecases.proxy_vtex import ProxyVtexUsecase


class ProxyVtexUsecaseTest(TestCase):
    def setUp(self):
        self.mock_service = MagicMock()
        self.mock_resolver = MagicMock()
        self.usecase = ProxyVtexUsecase(
            vtex_io_service=self.mock_service,
            context_resolver=self.mock_resolver,
        )

    def test_execute_returns_service_response(self):
        self.mock_resolver.execute.return_value = ("lojasrede", "lojasrede.myvtex.com")
        self.mock_service.proxy_vtex.return_value = {"ok": True}

        result = self.usecase.execute(
            method="GET",
            path="/api/oms/pvt/orders",
            project_uuid="project-uuid",
        )

        self.assertEqual(result, {"ok": True})
        self.mock_resolver.execute.assert_called_once_with(
            "project-uuid", merchant_name=None
        )
        self.mock_service.proxy_vtex.assert_called_once_with(
            account_domain="lojasrede.myvtex.com",
            vtex_account="lojasrede",
            method="GET",
            path="/api/oms/pvt/orders",
            headers=None,
            data=None,
            params=None,
        )

    def test_execute_uses_merchant_account_for_jwt_and_host(self):
        self.mock_resolver.execute.return_value = (
            "otherstore",
            "otherstore.myvtex.com",
        )
        self.mock_service.proxy_vtex.return_value = {"ok": True}

        result = self.usecase.execute(
            method="GET",
            path="/api/oms/pvt/orders",
            project_uuid="project-uuid",
            merchant_name="otherstore",
        )

        self.assertEqual(result, {"ok": True})
        self.mock_resolver.execute.assert_called_once_with(
            "project-uuid", merchant_name="otherstore"
        )
        self.mock_service.proxy_vtex.assert_called_once_with(
            account_domain="otherstore.myvtex.com",
            vtex_account="otherstore",
            method="GET",
            path="/api/oms/pvt/orders",
            headers=None,
            data=None,
            params=None,
        )

    def test_execute_raises_validation_error_when_context_invalid(self):
        self.mock_resolver.execute.side_effect = ValueError(
            "Project not found for given UUID."
        )

        with self.assertRaises(ValidationError):
            self.usecase.execute(
                method="GET",
                path="/api/oms/pvt/orders",
                project_uuid="invalid-uuid",
            )

        self.mock_service.proxy_vtex.assert_not_called()

    def test_execute_reraises_custom_api_exception(self):
        self.mock_resolver.execute.return_value = ("lojasrede", "lojasrede.myvtex.com")
        self.mock_service.proxy_vtex.side_effect = CustomAPIException(
            detail="upstream error",
            status_code=429,
        )

        with self.assertRaises(CustomAPIException) as ctx:
            self.usecase.execute(
                method="GET",
                path="/api/oms/pvt/orders",
                project_uuid="project-uuid",
            )

        self.assertEqual(ctx.exception.status_code, 429)

    def test_execute_wraps_unexpected_errors_as_custom_api_exception(self):
        self.mock_resolver.execute.return_value = ("lojasrede", "lojasrede.myvtex.com")
        self.mock_service.proxy_vtex.side_effect = RuntimeError("boom")

        with self.assertRaises(CustomAPIException) as ctx:
            self.usecase.execute(
                method="GET",
                path="/api/oms/pvt/orders",
                project_uuid="project-uuid",
            )

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("Unexpected proxy error", str(ctx.exception.detail))

    def test_defaults_context_resolver_from_service(self):
        from retail.vtex.usecases.resolve_proxy_context import (
            ResolveProxyContextUseCase,
        )

        usecase = ProxyVtexUsecase(vtex_io_service=MagicMock())
        self.assertIsInstance(usecase.context_resolver, ResolveProxyContextUseCase)
