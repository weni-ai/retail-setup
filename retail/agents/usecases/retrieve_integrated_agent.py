from uuid import UUID

from rest_framework.exceptions import NotFound

from retail.agents.models import IntegratedAgent


class RetrieveIntegratedAgentUseCase:
    def _get_integrated_agent(self, pk: UUID) -> IntegratedAgent:
        try:
            return IntegratedAgent.objects.get(uuid=pk)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Assigned agent not found: {pk}")

    def execute(self, pk: UUID) -> IntegratedAgent:
        return self._get_integrated_agent(pk)
