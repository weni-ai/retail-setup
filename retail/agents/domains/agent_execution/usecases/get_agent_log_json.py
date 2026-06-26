"""Use case: server-side proxy for a single log's stored JSON payload.

The client used to fetch the trace payload straight from a presigned S3
URL, which tripped S3's cross-origin restrictions. This use case reads
the object server-side instead, so the browser only ever talks to our
API. It owns the S3 read entirely and translates storage outcomes into
the HTTP-facing contract:

- row missing / outside the tenant -> ``NotFound`` (404)
- row has no stored payload, or the object is gone -> ``NotFound`` (404)
- unexpected S3 / decode failure -> ``APIException`` (500)
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from rest_framework.exceptions import APIException, NotFound

from retail.agents.domains.agent_execution.models import AgentExecution
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GetAgentLogJsonDTO:
    """Input DTO for ``GetAgentLogJsonUseCase``.

    ``agent_uuid`` / ``project_uuid`` scope the lookup to the tenant so a
    log can never be read across projects; ``log_uuid`` is the
    ``AgentExecution.uuid`` of the row whose payload is requested.
    """

    agent_uuid: UUID
    project_uuid: UUID
    log_uuid: UUID


class GetAgentLogJsonUseCase:
    """Fetch and return the stored JSON payload for a single log row."""

    def __init__(self, traces_storage: Optional[ExecutionTracesStorageService] = None):
        self._traces_storage = traces_storage

    @property
    def traces_storage(self) -> ExecutionTracesStorageService:
        """Build the S3-backed storage lazily.

        Constructing it resolves the trace bucket from settings, which
        fails loudly when storage is unconfigured. Deferring it keeps
        the not-found paths (missing row / empty key) from depending on
        S3 configuration, so they return 404 without ever touching S3.
        """
        if self._traces_storage is None:
            self._traces_storage = ExecutionTracesStorageService()
        return self._traces_storage

    def execute(self, dto: GetAgentLogJsonDTO) -> Any:
        execution = self._get_execution(dto)

        if not execution.traces_s3_key:
            raise NotFound(f"No stored payload for log: {dto.log_uuid}")

        content = self._read_payload(execution.traces_s3_key, dto.log_uuid)
        if content is None:
            raise NotFound(f"No stored payload for log: {dto.log_uuid}")

        return self._parse_payload(content, dto.log_uuid)

    def _get_execution(self, dto: GetAgentLogJsonDTO) -> AgentExecution:
        try:
            return AgentExecution.objects.get(
                uuid=dto.log_uuid,
                integrated_agent__uuid=dto.agent_uuid,
                integrated_agent__project__uuid=dto.project_uuid,
                integrated_agent__project__is_active=True,
            )
        except AgentExecution.DoesNotExist:
            raise NotFound(f"Log not found: {dto.log_uuid}")

    def _read_payload(self, s3_key: str, log_uuid: UUID) -> Optional[bytes]:
        try:
            return self.traces_storage.read_traces_payload(s3_key)
        except (BotoCoreError, ClientError) as exc:
            logger.error(
                f"[AGENT_LOGS] Failed to read payload for log {log_uuid}: {exc}"
            )
            raise APIException("Failed to read the log payload from storage.")

    @staticmethod
    def _parse_payload(content: bytes, log_uuid: UUID) -> Any:
        try:
            return json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.error(
                f"[AGENT_LOGS] Stored payload for log {log_uuid} is not valid JSON: {exc}"
            )
            raise APIException("Stored log payload is not valid JSON.")
