import logging
from typing import Any, Dict, Optional

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.api.integrated_agent.usecases.dto import SendTestTemplateDTO
from retail.services.flows.service import FlowsService
from retail.templates.models import Template

logger = logging.getLogger(__name__)


class SendTestTemplateUseCase:
    """Sends a test template message via WhatsApp broadcast."""

    def __init__(self, flows_service: Optional[FlowsService] = None):
        self._flows_service = flows_service or FlowsService()

    def execute(self, dto: SendTestTemplateDTO) -> None:
        integrated_agent = self._get_integrated_agent(dto.integrated_agent_uuid)
        template = self._get_active_template(integrated_agent)
        message = self._build_message(integrated_agent, template, dto)

        logger.info(
            f"Sending test template broadcast. "
            f"IntegratedAgent: {dto.integrated_agent_uuid}, "
            f"Template: {template.current_version.template_name}, "
            f"URNs count: {len(dto.contact_urns)}"
        )

        response = self._flows_service.send_whatsapp_broadcast(message)

        logger.info(
            f"Test template broadcast sent. "
            f"IntegratedAgent: {dto.integrated_agent_uuid}, "
            f"Response: {response}"
        )

    def _get_integrated_agent(self, uuid) -> IntegratedAgent:
        try:
            return IntegratedAgent.objects.select_related("project", "agent").get(
                uuid=uuid, is_active=True
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found: {uuid}")

    def _get_active_template(self, integrated_agent: IntegratedAgent) -> Template:
        template = (
            integrated_agent.templates.filter(
                is_active=True,
                current_version__isnull=False,
                current_version__status="APPROVED",
            )
            .select_related("current_version")
            .first()
        )

        if not template:
            raise ValidationError(
                {
                    "template": (
                        "No active approved template found "
                        f"for integrated agent {integrated_agent.uuid}."
                    )
                }
            )

        return template

    def _build_message(
        self,
        integrated_agent: IntegratedAgent,
        template: Template,
        dto: SendTestTemplateDTO,
    ) -> Dict[str, Any]:
        if not integrated_agent.channel_uuid:
            raise ValidationError(
                {
                    "channel_uuid": (
                        "Integrated agent has no channel configured: "
                        f"{integrated_agent.uuid}"
                    )
                }
            )

        message: Dict[str, Any] = {
            "project": str(integrated_agent.project.uuid),
            "urns": dto.contact_urns,
            "channel": str(integrated_agent.channel_uuid),
            "msg": {
                "template": {
                    "name": template.current_version.template_name,
                },
            },
        }

        language = self._resolve_language(template)
        if language:
            message["msg"]["template"]["locale"] = language

        if dto.variables:
            message["msg"]["template"]["variables"] = dto.variables

        return message

    def _resolve_language(self, template: Template) -> Optional[str]:
        if not template.metadata:
            return None

        language = template.metadata.get("language")
        if language:
            return language.replace("_", "-")

        return None
