"""S3 storage service for agent execution traces.

Each execution's traces are stored as a single JSON file produced by
the buffer flush — one PUT per execution, never read-modify-write.
Traces stay in Redis on the hot path and only land in S3 when
`flush_to_database` on the buffer calls `write_traces` here.

Storage goes through the S3 service layer (``S3ServiceInterface``)
rather than instantiating an ``S3Client`` directly. The service is
constructed once with the trace bucket binding (``EXECUTION_TRACES_BUCKET``)
so the bucket name lives in one place and tests can swap in a fake
without monkey-patching boto3.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.services.aws_s3.service import S3Service


logger = logging.getLogger(__name__)


def resolve_traces_bucket() -> str:
    """Return the configured bucket for execution traces or raise.

    Resolution order: ``EXECUTION_TRACES_BUCKET`` then
    ``AWS_STORAGE_BUCKET_NAME``. A missing/empty value fails loudly
    rather than routing writes to a placeholder bucket name.
    """
    bucket = getattr(settings, "EXECUTION_TRACES_BUCKET", None) or getattr(
        settings, "AWS_STORAGE_BUCKET_NAME", None
    )
    if not bucket:
        raise ImproperlyConfigured(
            "EXECUTION_TRACES_BUCKET (or AWS_STORAGE_BUCKET_NAME) must be set "
            "to persist agent execution traces."
        )
    return bucket


class ExecutionTracesStorageService:
    """Manage execution traces in S3.

    Traces are stored as a JSON array under ``executions/{uuid}/traces.json``.
    The key is deterministic from the execution UUID, so callers can
    reference it before the file actually exists.
    """

    def __init__(self, s3_service: Optional[S3ServiceInterface] = None):
        if s3_service is not None:
            self.s3_service = s3_service
        else:
            self.s3_service = S3Service(bucket_name=resolve_traces_bucket())

    def get_traces_key(self, execution_uuid: UUID) -> str:
        return f"executions/{execution_uuid}/traces.json"

    def write_traces(
        self,
        execution_uuid: UUID,
        traces: List[Dict[str, Any]],
        s3_key: Optional[str] = None,
    ) -> str:
        """Atomically replace the traces file for an execution.

        Used by the buffer at flush time to persist all traces in one
        S3 PUT, eliminating the previous per-trace read-modify-write.
        Raises on failure so the caller can defer the flush.
        """
        key = s3_key or self.get_traces_key(execution_uuid)
        content = json.dumps(traces, ensure_ascii=False).encode("utf-8")
        self.s3_service.put_object(key, content, content_type="application/json")
        logger.debug(
            "Wrote %d traces to S3 for execution %s", len(traces), execution_uuid
        )
        return key

    def read_traces_payload(self, s3_key: str) -> Optional[bytes]:
        """Return the raw stored traces bytes, or ``None`` when absent.

        Unlike ``get_traces`` (which swallows every failure into ``[]``
        for ops convenience), this surfaces the missing-object case as
        ``None`` and lets genuine S3 errors propagate, so the proxy
        endpoint can distinguish a ``404`` (no payload) from a ``500``
        (unexpected read failure).
        """
        return self.s3_service.get_object(s3_key)

    def get_traces(
        self, execution_uuid: UUID, s3_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        key = s3_key or self.get_traces_key(execution_uuid)

        try:
            content = self.s3_service.get_object(key)

            if content is None:
                logger.warning(f"Traces file not found for {execution_uuid}")
                return []

            return json.loads(content.decode("utf-8"))

        except json.JSONDecodeError as e:
            logger.error(f"Error parsing traces JSON for {execution_uuid}: {e}")
            return []
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Error retrieving traces for {execution_uuid}: {e}")
            return []
