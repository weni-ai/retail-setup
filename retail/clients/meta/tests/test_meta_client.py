"""Tests for ``MetaClient.fetch_library_template_by_name_and_language``.

Pinned by T015: exercises the exact-match post-filter the Direct Send
path relies on per ``contracts/meta-library-catalog.md`` §3.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from retail.clients.exceptions import CustomAPIException
from retail.clients.meta.client import MetaClient


class FetchLibraryTemplateByNameAndLanguageTest(TestCase):
    def setUp(self):
        self.client = MetaClient(token="test-token", url="https://graph.test")

    def _build_response(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        return response

    @patch.object(MetaClient, "make_request")
    def test_returns_exact_name_match_among_fuzzy_hits(self, mock_make_request):
        mock_make_request.return_value = self._build_response(
            {
                "data": [
                    {
                        "name": "weni_order_shipped_v2",
                        "language": "pt_BR",
                        "body": "Other template",
                    },
                    {
                        "name": "weni_order_shipped",
                        "language": "pt_BR",
                        "body": "Olá {{1}}, seu pedido foi enviado.",
                    },
                ]
            }
        )

        result = self.client.fetch_library_template_by_name_and_language(
            "weni_order_shipped", "pt_BR"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "weni_order_shipped")
        self.assertEqual(result["language"], "pt_BR")

    @patch.object(MetaClient, "make_request")
    def test_returns_none_when_no_exact_name_match(self, mock_make_request):
        mock_make_request.return_value = self._build_response(
            {
                "data": [
                    {
                        "name": "weni_order_shipped_v2",
                        "language": "pt_BR",
                        "body": "Other template",
                    }
                ]
            }
        )

        result = self.client.fetch_library_template_by_name_and_language(
            "weni_order_shipped", "pt_BR"
        )

        self.assertIsNone(result)

    @patch.object(MetaClient, "make_request")
    def test_returns_none_when_language_does_not_match(self, mock_make_request):
        mock_make_request.return_value = self._build_response(
            {
                "data": [
                    {
                        "name": "weni_order_shipped",
                        "language": "pt_BR",
                        "body": "Olá {{1}}.",
                    }
                ]
            }
        )

        result = self.client.fetch_library_template_by_name_and_language(
            "weni_order_shipped", "es_MX"
        )

        self.assertIsNone(result)

    @patch.object(MetaClient, "make_request")
    def test_returns_none_when_data_is_empty(self, mock_make_request):
        mock_make_request.return_value = self._build_response({"data": []})

        result = self.client.fetch_library_template_by_name_and_language(
            "weni_order_shipped", "pt_BR"
        )

        self.assertIsNone(result)

    @patch.object(MetaClient, "make_request")
    def test_accepts_match_when_response_omits_language_field(self, mock_make_request):
        mock_make_request.return_value = self._build_response(
            {
                "data": [
                    {
                        "name": "weni_order_shipped",
                        "body": "Olá {{1}}.",
                    }
                ]
            }
        )

        result = self.client.fetch_library_template_by_name_and_language(
            "weni_order_shipped", "pt_BR"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "weni_order_shipped")

    @patch.object(MetaClient, "make_request")
    def test_propagates_custom_api_exception(self, mock_make_request):
        mock_make_request.side_effect = CustomAPIException(
            detail="auth failure", status_code=403
        )

        with self.assertRaises(CustomAPIException):
            self.client.fetch_library_template_by_name_and_language(
                "weni_order_shipped", "pt_BR"
            )

    @patch.object(MetaClient, "make_request")
    def test_calls_message_template_library_endpoint_with_search_and_language(
        self, mock_make_request
    ):
        mock_make_request.return_value = self._build_response({"data": []})

        self.client.fetch_library_template_by_name_and_language(
            "weni_order_shipped", "es_MX"
        )

        mock_make_request.assert_called_once()
        kwargs = mock_make_request.call_args.kwargs
        self.assertEqual(kwargs["method"], "GET")
        self.assertIn("/message_template_library/", kwargs["url"])
        self.assertEqual(kwargs["params"]["search"], "weni_order_shipped")
        self.assertEqual(kwargs["params"]["language"], "es_MX")
