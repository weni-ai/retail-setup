"""Use cases for the agent-logs export download link.

The export-ready email used to embed a presigned S3 URL directly. Signed
with the pod's temporary credentials, that URL died when the session
token expired, so the advertised multi-day link broke within hours.

Instead, the email now points at our own always-on download endpoint
carrying a signed token (``BuildExportDownloadUrlUseCase``). When the
recipient clicks it, the endpoint verifies the token and mints a fresh,
short-lived presigned URL on the spot (``ResolveExportDownloadUseCase``),
then redirects to it. The link's lifetime therefore lives in a token we
sign with ``SECRET_KEY`` and is fully decoupled from AWS's session-token
TTL.
"""

import logging
from typing import Optional
from urllib.parse import quote

from django.conf import settings
from django.core import signing
from django.urls import reverse
from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_execution.usecases.export_agent_logs import (
    _resolve_export_bucket,
)
from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.services.aws_s3.service import S3Service


logger = logging.getLogger(__name__)


# Salt namespaces the signature so a token minted here can't be replayed
# against any other ``django.core.signing`` consumer sharing SECRET_KEY.
EXPORT_DOWNLOAD_SALT = "agent-logs-export-download"

# The signed link stays valid for the full week the export file is
# retained in S3 (matching the bucket's lifecycle rule). After that the
# object is gone, so a longer token would be useless anyway.
EXPORT_DOWNLOAD_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7

# The presigned URL is consumed by the redirect within seconds, so a
# short lifetime is plenty — and keeps it well inside the pod's
# session-token validity.
DOWNLOAD_PRESIGN_TTL_SECONDS = 5 * 60

# Reverse-resolved route name for the download endpoint.
DOWNLOAD_URL_NAME = "agent-logs-export-download"


class BuildExportDownloadUrlUseCase:
    """Build the signed, app-hosted download URL emailed to the user."""

    def execute(self, key: str) -> str:
        token = signing.dumps({"key": key}, salt=EXPORT_DOWNLOAD_SALT)
        path = reverse(DOWNLOAD_URL_NAME)
        return f"{settings.DOMAIN.rstrip('/')}{path}?token={quote(token)}"


class ResolveExportDownloadUseCase:
    """Verify a download token and mint a fresh presigned URL for it."""

    def __init__(self, s3_service: Optional[S3ServiceInterface] = None):
        self.s3_service = s3_service or S3Service(bucket_name=_resolve_export_bucket())

    def execute(self, token: str) -> str:
        key = self._resolve_key(token)
        return self.s3_service.generate_presigned_url(
            key, expiration=DOWNLOAD_PRESIGN_TTL_SECONDS
        )

    @staticmethod
    def _resolve_key(token: str) -> str:
        try:
            payload = signing.loads(
                token,
                salt=EXPORT_DOWNLOAD_SALT,
                max_age=EXPORT_DOWNLOAD_TOKEN_TTL_SECONDS,
            )
        except signing.SignatureExpired:
            raise NotFound("This download link has expired.")
        except signing.BadSignature:
            raise NotFound("Invalid download link.")

        return payload["key"]
