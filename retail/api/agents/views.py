from rest_framework.response import Response
from weni_commons.auth import IsWeniAuthenticated

from retail.api.agents.usecases.list_agents_for_project import (
    ListAgentsForProjectUseCase,
)
from retail.api.base_service_view import BaseServiceView
from retail.internal.permissions import HasWeniProjectPermission
from retail.internal.weni_mixins import WeniAuthMixin


class AgentsView(WeniAuthMixin, BaseServiceView):
    """
    View to list available agents for a project.

    Returns agents from Nexus service and gallery agents (CLI-pushed agents).
    This is the dedicated endpoint for agent listing, replacing the legacy
    features endpoint for VTEX integrations. The project scope is read from the
    authenticated context (``self.auth``).
    """

    permission_classes = [IsWeniAuthenticated, HasWeniProjectPermission]

    def get(self, request, project_uuid: str):
        use_case = ListAgentsForProjectUseCase(nexus_service=self.nexus_service)
        result = use_case.execute(self.auth.project_uuid)

        return Response(result.to_dict())
