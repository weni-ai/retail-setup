"""End-to-end tests for ``GET /logs/export/download/``.

The endpoint is public and token-authorized: it validates the signed
token, mints a fresh presigned URL via ``ResolveExportDownloadUseCase``,
and 302-redirects to it. These tests pin that loop without any platform
authentication, mirroring a click straight from the export email.
"""

from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.test import APITestCase


class AgentLogsExportDownloadViewTest(APITestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("agent-logs-export-download")

    @patch(
        "retail.agents.domains.agent_execution.views.ResolveExportDownloadUseCase"
    )
    def test_valid_token_redirects_to_fresh_presigned_url(self, mock_use_case_cls):
        mock_use_case_cls.return_value.execute.return_value = "https://s3/presigned"

        response = self.client.get(self.url, {"token": "signed-token"})

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response["Location"], "https://s3/presigned")
        mock_use_case_cls.return_value.execute.assert_called_once_with("signed-token")

    def test_missing_token_returns_400(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(
        "retail.agents.domains.agent_execution.views.ResolveExportDownloadUseCase"
    )
    def test_invalid_token_returns_404(self, mock_use_case_cls):
        mock_use_case_cls.return_value.execute.side_effect = NotFound("bad")

        response = self.client.get(self.url, {"token": "bad-token"})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
