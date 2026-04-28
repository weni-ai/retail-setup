import logging

from dataclasses import dataclass
from typing import Any, Dict, Optional

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.broadcasts.models import BroadcastMessage, BroadcastStatus
from retail.templates.models import Template

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecordBroadcastSentDTO:
    """Input DTO for persisting a broadcast right after dispatch.

    ``error_message`` is populated only on the failure path; when present
    the row is recorded with status=FAILED instead of SENT.
    """

    broadcast_id: Optional[int]
    integrated_agent: IntegratedAgent
    template: Optional[Template]
    contact_urn: str
    channel_uuid: Optional[str]
    flows_template_uuid: Optional[str]
    flows_response: Dict[str, Any]
    error_message: str = ""


class RecordBroadcastSentUseCase:
    """Persists a BroadcastMessage row immediately after a dispatch attempt.

    Two outcomes are recorded:
      - status=SENT  → Flows accepted the broadcast and returned a
                       broadcast_id. The external_message_id is filled
                       later by the status consumer on the first courier
                       create event.
      - status=FAILED → Flows raised an exception or returned no
                       broadcast_id. ``error_message`` carries the
                       short reason; ``last_payload`` keeps the raw
                       response for diagnostics.
    """

    def execute(self, dto: RecordBroadcastSentDTO) -> Optional[BroadcastMessage]:
        integrated_agent = dto.integrated_agent
        project = integrated_agent.project
        project_uuid = str(project.uuid)
        vtex_account = project.vtex_account

        template_name, template_version = self._resolve_template_identity(dto.template)

        # A missing broadcast_id means we cannot link this row to a
        # courier event later, so it is treated as a dispatch failure
        # even if the original call did not raise.
        is_failure = bool(dto.error_message) or dto.broadcast_id is None
        status = BroadcastStatus.FAILED if is_failure else BroadcastStatus.SENT

        error_message = dto.error_message
        if is_failure and not error_message:
            error_message = "Flows response missing broadcast_id"
            logger.error(
                f"[BROADCAST_TRACKING] dispatch_failed: missing broadcast_id "
                f"project_uuid={project_uuid} vtex_account={vtex_account} "
                f"agent_uuid={integrated_agent.uuid} template={template_name} "
                f"response={dto.flows_response}"
            )

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
        )

        logger.info(
            f"[BROADCAST_TRACKING] recorded: "
            f"broadcast_uuid={broadcast_message.uuid} "
            f"status={status} broadcast_id={dto.broadcast_id} "
            f"project_uuid={project_uuid} vtex_account={vtex_account} "
            f"agent_uuid={integrated_agent.uuid} template={template_name} "
            f"contact_urn={dto.contact_urn}"
        )

        return broadcast_message

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
