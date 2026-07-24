from unittest.mock import MagicMock, patch

from django.test import TestCase

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
