from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from retail.clients.exceptions import CustomAPIException
from retail.clients.vtex_io.client import VtexIOClient


class VtexIOClientProxyResponseTest(TestCase):
    def setUp(self):
        self.client = VtexIOClient(jwt_usecase=MagicMock())
        self.client.jwt_usecase.generate_proxy_vtex_jwt_token.return_value = "token"

    def test_jwt_headers_include_accept_encoding_identity(self):
        headers = self.client._get_jwt_headers("lojasrede")

        self.assertEqual(headers["Accept-Encoding"], "identity")

    @patch.object(VtexIOClient, "make_request")
    def test_cleanup_availability_notify_posts_to_io_route(self, mock_make_request):
        response = MagicMock()
        response.json.return_value = {"deleted": 1, "scanned": 2, "skipped": False}
        mock_make_request.return_value = response

        result = self.client.cleanup_availability_notify(
            account_domain="lojasrede.myvtex.com",
            vtex_account="lojasrede",
        )

        mock_make_request.assert_called_once()
        args, kwargs = mock_make_request.call_args
        self.assertEqual(kwargs.get("method") or args[1], "POST")
        url = args[0] if args else kwargs.get("url")
        self.assertIn("/_v/availability-notify/cleanup", url)
        self.assertEqual(result, {"deleted": 1, "scanned": 2, "skipped": False})

    @patch.object(VtexIOClient, "make_request")
    @override_settings(VTEX_IO_WORKSPACE="weni")
    def test_install_back_in_stock_app_posts_production_host(self, mock_make_request):
        response = MagicMock()
        response.json.return_value = {
            "app": "vtex.agentic-cx-back-in-stock@0.x",
            "installed": True,
        }
        mock_make_request.return_value = response

        result = self.client.install_back_in_stock_app("recorrenciacharlie")

        mock_make_request.assert_called_once()
        args, kwargs = mock_make_request.call_args
        self.assertEqual(
            args[0],
            "https://recorrenciacharlie.myvtex.com/_v/back-in-stock/app/install",
        )
        self.assertEqual(kwargs["method"], "POST")
        self.assertEqual(kwargs["headers"]["X-Weni-Auth"], "token")
        self.assertNotIn("weni--", args[0])
        self.assertEqual(result["installed"], True)

    @patch.object(VtexIOClient, "make_request")
    def test_uninstall_back_in_stock_app_posts_production_host(self, mock_make_request):
        response = MagicMock()
        response.json.return_value = {
            "app": "vtex.agentic-cx-back-in-stock@0.x",
            "uninstalled": True,
        }
        mock_make_request.return_value = response

        result = self.client.uninstall_back_in_stock_app("recorrenciacharlie")

        args, kwargs = mock_make_request.call_args
        self.assertEqual(
            args[0],
            "https://recorrenciacharlie.myvtex.com/_v/back-in-stock/app/uninstall",
        )
        self.assertEqual(kwargs["headers"]["X-Weni-Auth"], "token")
        self.assertEqual(result["uninstalled"], True)

    @patch.object(VtexIOClient, "make_request")
    def test_proxy_vtex_raises_custom_api_exception_on_invalid_json(
        self, mock_make_request
    ):
        response = MagicMock()
        response.status_code = 200
        response.text = "not-json"
        response.json.side_effect = ValueError("invalid json")
        mock_make_request.return_value = response

        with self.assertRaises(CustomAPIException) as ctx:
            self.client.proxy_vtex(
                account_domain="lojasrede.myvtex.com",
                vtex_account="lojasrede",
                method="GET",
                path="/api/oms/pvt/orders",
            )

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertEqual(ctx.exception.detail, "VTEX IO returned a non-JSON response")
