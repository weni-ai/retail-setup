import logging

from dataclasses import dataclass
from typing import Any, Dict, Optional

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.broadcasts.models import BroadcastMessage, BroadcastStatus
from retail.broadcasts.services.flows_status_mapper import FlowsStatusMapper
from retail.templates.models import Template

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BroadcastDispatchContext:
    """Commercial context of a broadcast at dispatch time.

    Captures the VTEX identifiers that originated the broadcast so a
    later ``invoiced`` event can be attributed back to it. Both fields
    are optional because a broadcast may legitimately have neither
    (e.g. generic webhook with no commercial intent), only one
    (abandoned cart only knows ``order_form_id``; order-status only
    knows ``order_id``), or both (rare, but allowed).
    """

    order_form_id: Optional[str] = None
    order_id: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.order_form_id and not self.order_id


@dataclass(frozen=True)
class RecordBroadcastSentDTO:
    """Input DTO for persisting a broadcast right after dispatch.

    ``error_message`` is populated only on the failure path; when present
    the row is recorded with status=FAILED regardless of what the Flows
    response says.

    ``dispatch_context`` carries the commercial origin (order_form_id /
    order_id) so the row can later be matched against an ``invoiced``
    event for conversion attribution.
    """

    broadcast_id: Optional[int]
    integrated_agent: IntegratedAgent
    template: Optional[Template]
    contact_urn: str
    channel_uuid: Optional[str]
    flows_template_uuid: Optional[str]
    flows_response: Dict[str, Any]
    error_message: str = ""
    dispatch_context: Optional[BroadcastDispatchContext] = None


class RecordBroadcastSentUseCase:
    """Persists a BroadcastMessage row immediately after a dispatch attempt.

    The persisted ``status`` mirrors the actual state reported by the
    Flows API (queued/sent/failed) instead of being hardcoded. The
    courier later transitions the row through DELIVERED/READ via the
    msgs.topic exchange.

    Failure cases are normalized to ``FAILED``:
      - Flows raised before returning (caller passes ``error_message``).
      - Flows returned a response without ``broadcast_id`` (we cannot
        link this row to a courier event later, so the dispatch is
        useless even if the HTTP call succeeded).
      - Flows response status was explicitly ``"failed"``.
    """

    def execute(self, dto: RecordBroadcastSentDTO) -> Optional[BroadcastMessage]:
        integrated_agent = dto.integrated_agent
        project = integrated_agent.project
        project_uuid = str(project.uuid)
        vtex_account = project.vtex_account

        template_name, template_version = self._resolve_template_identity(dto.template)

        status, error_message = self._resolve_status_and_error(
            dto=dto,
            project_uuid=project_uuid,
            vtex_account=vtex_account,
            template_name=template_name,
        )

        order_form_id, order_id = self._resolve_dispatch_context(dto.dispatch_context)

        broadcast_message = BroadcastMessage.objects.create(
            broadcast_id=dto.broadcast_id,
            project=project,
            integrated_agent=integrated_agent,
            template_name=template_name,
            template_version=template_version,
            flows_template_uuid=dto.flows_template_uuid,
            channel_uuid=dto.channel_uuid,
            contact_urn=dto.contact_urn or "",
            status=status,
            error_message=error_message,
            last_payload={"flows_response": dto.flows_response},
            order_form_id=order_form_id,
            order_id=order_id,
        )

        logger.info(
            f"[BROADCAST_TRACKING] recorded: "
            f"broadcast_uuid={broadcast_message.uuid} "
            f"status={status} broadcast_id={dto.broadcast_id} "
            f"project_uuid={project_uuid} vtex_account={vtex_account} "
            f"agent_uuid={integrated_agent.uuid} template={template_name} "
            f"contact_urn={dto.contact_urn} "
            f"order_form_id={order_form_id} order_id={order_id}"
        )

        return broadcast_message

    @staticmethod
    def _resolve_dispatch_context(
        dispatch_context: Optional[BroadcastDispatchContext],
    ) -> tuple[Optional[str], Optional[str]]:
        """Return ``(order_form_id, order_id)`` from the dispatch context.

        Both fields are stored as nullable on the row so a missing
        context (generic webhook, manual dispatch) leaves both as NULL
        and the conversion lookup naturally skips it.
        """
        if dispatch_context is None or dispatch_context.is_empty:
            return None, None
        return dispatch_context.order_form_id, dispatch_context.order_id

    def _resolve_status_and_error(
        self,
        dto: RecordBroadcastSentDTO,
        project_uuid: str,
        vtex_account: Optional[str],
        template_name: str,
    ) -> tuple[BroadcastStatus, str]:
        """Decide the persisted status + error_message from the dispatch outcome.

        Order of precedence:
          1. Caller-supplied ``error_message`` → FAILED.
          2. Missing broadcast_id in the Flows response → FAILED with a
             synthetic reason (we cannot link this row to courier events later).
          3. Otherwise, mirror the Flows response status via FlowsStatusMapper.
        """
        if dto.error_message:
            return BroadcastStatus.FAILED, dto.error_message

        if dto.broadcast_id is None:
            self._log_missing_broadcast_id(
                dto=dto,
                project_uuid=project_uuid,
                vtex_account=vtex_account,
                template_name=template_name,
            )
            return BroadcastStatus.FAILED, "Flows response missing broadcast_id"

        flows_status = (dto.flows_response or {}).get("status")
        mapped = FlowsStatusMapper.map(flows_status) or BroadcastStatus.QUEUED

        if mapped == BroadcastStatus.FAILED:
            return mapped, self._extract_failure_reason_from_response(dto)

        return mapped, ""

    @staticmethod
    def _extract_failure_reason_from_response(
        dto: RecordBroadcastSentDTO,
    ) -> str:
        """Pull a human-readable error from the Flows response body so a
        row with status=FAILED never ends up with an empty error_message.

        Falls back to a synthetic message when the response carries no
        usable error/message field.
        """
        response = dto.flows_response or {}
        for key in ("error", "message", "detail"):
            value = response.get(key)
            if value:
                return str(value)
        return "Flows reported status=failed without error detail"

    @staticmethod
    def _log_missing_broadcast_id(
        dto: RecordBroadcastSentDTO,
        project_uuid: str,
        vtex_account: Optional[str],
        template_name: str,
    ) -> None:
        """Emit a per-dispatch log line when the Flows response carries
        no broadcast_id; this row will exist only for diagnostics since
        no courier event can ever be linked to it."""
        logger.error(
            f"[BROADCAST_TRACKING] dispatch_failed: missing broadcast_id "
            f"project_uuid={project_uuid} vtex_account={vtex_account} "
            f"agent_uuid={dto.integrated_agent.uuid} template={template_name} "
            f"response={dto.flows_response}"
        )

    @staticmethod
    def _resolve_template_identity(template: Optional[Template]) -> tuple[str, str]:
        """Split template identity into raw name and Meta version name.

        - ``template_name`` is the raw local name (e.g. "abandoned_cart").
        - ``template_version`` is the full Meta name stored on the current
          Version (e.g. "weni_abandoned_cart_1768996789226396").
        """
        if template is None:
            return "", ""

        name = template.name or ""
        version = ""
        current_version = getattr(template, "current_version", None)
        if current_version is not None:
            version = getattr(current_version, "template_name", "") or ""
        return name, version
