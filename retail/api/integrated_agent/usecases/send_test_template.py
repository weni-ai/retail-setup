import logging
from typing import Any, Dict, Optional

from django.conf import settings

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
            )
            .select_related("current_version")
            .first()
        )

        status = template.current_version.status if template else "NOT_FOUND"

        if status == "APPROVED":
            return template

        raise ValidationError(
            {
                "template": (
                    f"No active approved template for integrated agent "
                    f"{integrated_agent.uuid} (version_status={status})."
                )
            }
        )

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

        self._apply_test_button(template, message)
        self._apply_header_image(template, message)

        return message

    def _apply_test_button(self, template: Template, message: Dict[str, Any]) -> None:
        """
        Add a test button parameter when the template has a URL button
        (e.g. abandoned cart checkout link).
        """
        buttons = (template.metadata or {}).get("buttons", [])
        has_url_button = any(b.get("type") == "URL" for b in buttons)

        if has_url_button:
            message["msg"]["buttons"] = [
                {
                    "sub_type": "url",
                    "parameters": [{"type": "text", "text": "example123"}],
                }
            ]

    def _apply_header_image(self, template: Template, message: Dict[str, Any]) -> None:
        """
        Add the default placeholder image when the template header
        expects an image.
        """
        header = (template.metadata or {}).get("header")
        if not header or header.get("header_type") != "IMAGE":
            return

        image_url = settings.ABANDONED_CART_DEFAULT_IMAGE_URL
        message["msg"]["attachments"] = [f"image/png:{image_url}"]

    def _resolve_language(self, template: Template) -> Optional[str]:
        if not template.metadata:
            return None

        language = template.metadata.get("language")
        if language:
            return language.replace("_", "-")

        return None
