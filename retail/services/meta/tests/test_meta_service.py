"""Tests for ``MetaService.fetch_library_template_by_name_and_language``.

Pinned by T016: the service is the boundary that swallows
infrastructure exceptions and returns ``None`` per
``contracts/meta-library-catalog.md`` §4. Use cases never see HTTP
details (Constitution Principle I — Service contract).
"""

import logging

from unittest.mock import MagicMock

from django.test import TestCase

from retail.clients.exceptions import CustomAPIException
from retail.services.meta.service import MetaService


class FetchLibraryTemplateByNameAndLanguageServiceTest(TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.service = MetaService(client=self.client)

    def test_returns_client_payload_on_success(self):
        payload = {"name": "weni_order_shipped", "language": "pt_BR", "body": "..."}
        self.client.fetch_library_template_by_name_and_language.return_value = payload

        result = self.service.fetch_library_template_by_name_and_language(
            "weni_order_shipped", "pt_BR"
        )

        self.assertEqual(result, payload)
        self.client.fetch_library_template_by_name_and_language.assert_called_once_with(
            "weni_order_shipped", "pt_BR"
        )

    def test_returns_none_on_custom_api_exception_and_logs_error(self):
        self.client.fetch_library_template_by_name_and_language.side_effect = (
            CustomAPIException(detail="auth failure", status_code=403)
        )

        with self.assertLogs(
            "retail.services.meta.service", level=logging.ERROR
        ) as captured:
            result = self.service.fetch_library_template_by_name_and_language(
                "weni_order_shipped", "pt_BR"
            )

        self.assertIsNone(result)
        joined_logs = "\n".join(captured.output)
        self.assertIn("weni_order_shipped", joined_logs)
        self.assertIn("pt_BR", joined_logs)

    def test_returns_none_on_malformed_payload_and_logs_error(self):
        self.client.fetch_library_template_by_name_and_language.side_effect = (
            ValueError("unexpected payload shape")
        )

        with self.assertLogs(
            "retail.services.meta.service", level=logging.ERROR
        ) as captured:
            result = self.service.fetch_library_template_by_name_and_language(
                "weni_order_shipped", "pt_BR"
            )

        self.assertIsNone(result)
        joined_logs = "\n".join(captured.output)
        self.assertIn("weni_order_shipped", joined_logs)
        self.assertIn("pt_BR", joined_logs)
