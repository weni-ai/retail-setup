from typing import TypedDict

from rest_framework.exceptions import NotFound, ValidationError

from uuid import UUID

from retail.agents.models import IntegratedAgent


class UpdateIntegratedAgentData(TypedDict):
    contact_percentage: int


class UpdateIntegratedAgentUseCase:
    def _get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        try:
            return IntegratedAgent.objects.get(
                uuid=integrated_agent_uuid, is_active=True
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found {integrated_agent_uuid}")

    def _is_valid_percentage(self, percentage: int) -> bool:
        return 0 <= percentage <= 100

    def execute(
        self, integrated_agent_uuid: UUID, data: UpdateIntegratedAgentData
    ) -> IntegratedAgent:
        integrated_agent = self._get_integrated_agent(integrated_agent_uuid)

        if not self._is_valid_percentage(data["contact_percentage"]):
            raise ValidationError({"contact_percentage": "Invalid percentage"})

        integrated_agent.contact_percentage = data["contact_percentage"]
        integrated_agent.save()
        return integrated_agent
