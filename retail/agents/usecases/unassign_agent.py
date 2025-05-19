from rest_framework.exceptions import NotFound

from retail.agents.models import IntegratedAgent, Agent


class UnassignAgentUseCase:
    def _get_integrated_agent(self, agent: Agent, project_uuid: str) -> IntegratedAgent:
        try:
            return IntegratedAgent.objects.get(agent=agent, project__uuid=project_uuid)
        except IntegratedAgent.DoesNotExist:
            raise NotFound("Integrated agent not found")

    def execute(self, agent: Agent, project_uuid: str) -> None:
        integrated_agent = self._get_integrated_agent(agent, project_uuid)
        integrated_agent.delete()
