"""Tests for the agent-logs export download use cases.

``BuildExportDownloadUrlUseCase`` signs the uploaded S3 key into a stable
URL pointing at our own download endpoint; ``ResolveExportDownloadUseCase``
verifies that token on click and mints a fresh, short-lived presigned URL.
Together they keep the link's lifetime under our control (a signed token)
instead of AWS's session-token TTL.
"""

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from django.core import signing
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_execution.usecases import export_download
from retail.agents.domains.agent_execution.usecases.export_download import (
    DOWNLOAD_PRESIGN_TTL_SECONDS,
    EXPORT_DOWNLOAD_SALT,
    BuildExportDownloadUrlUseCase,
    ResolveExportDownloadUseCase,
)


@override_settings(DOMAIN="https://example.com", SECRET_KEY="test-secret-key")
class BuildExportDownloadUrlUseCaseTests(SimpleTestCase):
    def test_url_points_at_download_endpoint_with_signed_key(self):
        key = "exports/agent_logs/p/a/20260101T000000Z.csv"

        url = BuildExportDownloadUrlUseCase().execute(key)

        parsed = urlparse(url)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}", "https://example.com")
        self.assertEqual(parsed.path, reverse("agent-logs-export-download"))

        token = parse_qs(parsed.query)["token"][0]
        payload = signing.loads(token, salt=EXPORT_DOWNLOAD_SALT)
        self.assertEqual(payload, {"key": key})

    @override_settings(DOMAIN="https://example.com/")
    def test_trailing_slash_on_domain_does_not_double_up(self):
        url = BuildExportDownloadUrlUseCase().execute("some/key.csv")

        self.assertTrue(url.startswith("https://example.com/api/"))
        self.assertNotIn("example.com//", url)


@override_settings(SECRET_KEY="test-secret-key")
class ResolveExportDownloadUseCaseTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.fake_s3 = MagicMock()
        self.fake_s3.generate_presigned_url.return_value = "https://s3/presigned"
        self.use_case = ResolveExportDownloadUseCase(s3_service=self.fake_s3)
        self.key = "exports/agent_logs/p/a/file.csv"
        self.token = signing.dumps({"key": self.key}, salt=EXPORT_DOWNLOAD_SALT)

    def test_valid_token_mints_short_lived_presigned_url(self):
        result = self.use_case.execute(self.token)

        self.assertEqual(result, "https://s3/presigned")
        self.fake_s3.generate_presigned_url.assert_called_once_with(
            self.key, expiration=DOWNLOAD_PRESIGN_TTL_SECONDS
        )

    def test_expired_token_raises_not_found(self):
        # A negative max_age means any token already counts as expired,
        # exercising the real ``SignatureExpired`` branch.
        with patch.object(export_download, "EXPORT_DOWNLOAD_TOKEN_TTL_SECONDS", -1):
            with self.assertRaises(NotFound):
                self.use_case.execute(self.token)

        self.fake_s3.generate_presigned_url.assert_not_called()

    def test_tampered_token_raises_not_found(self):
        with self.assertRaises(NotFound):
            self.use_case.execute(self.token + "tampered")

        self.fake_s3.generate_presigned_url.assert_not_called()

    def test_token_signed_with_other_salt_raises_not_found(self):
        foreign_token = signing.dumps({"key": self.key}, salt="some-other-salt")

        with self.assertRaises(NotFound):
            self.use_case.execute(foreign_token)

        self.fake_s3.generate_presigned_url.assert_not_called()

    @override_settings(AWS_STORAGE_BUCKET_NAME="export-bucket")
    @patch("retail.agents.domains.agent_execution.usecases.export_download.S3Service")
    def test_default_constructor_binds_export_bucket(self, mock_s3_service):
        ResolveExportDownloadUseCase()

        mock_s3_service.assert_called_once_with(bucket_name="export-bucket")
