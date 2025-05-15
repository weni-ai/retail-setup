from django.db.models import QuerySet

from uuid import UUID

from rest_framework.exceptions import NotFound

from retail.agents.models import Agent


class RetrieveAgentUseCase:
    @staticmethod
    def execute(agent_uuid: UUID) -> QuerySet[Agent]:
        try:
            return Agent.objects.get(uuid=agent_uuid)
        except Agent.DoesNotExist:
            raise NotFound(f"Agente not found: {str(agent_uuid)}")
