from rest_framework.response import Response

from retail.api.agents.usecases.list_agents_for_project import (
    ListAgentsForProjectUseCase,
)
from retail.api.base_service_view import BaseServiceView


class AgentsView(BaseServiceView):
    """
    View to list available agents for a project.

    Returns agents from Nexus service and gallery agents (CLI-pushed agents).
    This is the dedicated endpoint for agent listing, replacing the legacy
    features endpoint for VTEX integrations.
    """

    def get(self, request, project_uuid: str):
        use_case = ListAgentsForProjectUseCase(nexus_service=self.nexus_service)
        result = use_case.execute(str(project_uuid))

        return Response(result.to_dict())
