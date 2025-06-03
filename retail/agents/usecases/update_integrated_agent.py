from typing import TypedDict, Optional

from rest_framework.exceptions import NotFound, ValidationError

from uuid import UUID

from retail.agents.models import IntegratedAgent


class UpdateIntegratedAgentData(TypedDict):
    contact_percentage: Optional[int]
    is_published: Optional[bool]


class UpdateIntegratedAgentUseCase:
    def _get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        try:
            return IntegratedAgent.objects.get(
                uuid=integrated_agent_uuid, is_active=True
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found {integrated_agent_uuid}")

    def _update_contact_percentage(
        self, integrated_agent: IntegratedAgent, contact_percentage: int
    ) -> None:
        if not 0 <= contact_percentage <= 100:
            raise ValidationError({"contact_percentage": "Invalid percentage"})

        integrated_agent.contact_percentage = contact_percentage

    def _update_is_published(
        self, integrated_agent: IntegratedAgent, is_published: bool
    ) -> None:
        integrated_agent.is_published = is_published

    def execute(
        self, integrated_agent_uuid: UUID, data: UpdateIntegratedAgentData
    ) -> IntegratedAgent:
        integrated_agent = self._get_integrated_agent(integrated_agent_uuid)
        contact_percentage = data.get("contact_percentage", None)
        is_published = data.get("is_published", None)

        if contact_percentage is not None:
            self._update_contact_percentage(integrated_agent, contact_percentage)

        if is_published is not None:
            self._update_is_published(integrated_agent, is_published)

        integrated_agent.save()
        return integrated_agent
