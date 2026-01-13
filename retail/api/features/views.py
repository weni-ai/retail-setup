import logging

from rest_framework import status
from rest_framework.response import Response

from retail.agents.domains.agent_management.serializers import GalleryAgentSerializer
from retail.agents.domains.agent_management.usecases.list import (
    ListAgentsUseCase,
)
from retail.api.base_service_view import BaseServiceView
from retail.api.features.serializers import FeatureQueryParamsSerializer
from retail.projects.models import Project

logger = logging.getLogger(__name__)


class FeaturesView(BaseServiceView):
    """
    TODO: This view is deprecated and will be removed in a future version.
    Use AgentsView (/v2/agents/<project_uuid>/) instead.
    Features are no longer listed - only agents (nexus_agents and gallery_agents).
    """

    def get(self, request, project_uuid: str):
        try:
            serializer = FeatureQueryParamsSerializer(data=request.query_params)
            serializer.is_valid(raise_exception=True)
            params = serializer.validated_data

            nexus_agents = params.get("nexus_agents")

            project = Project.objects.get(uuid=project_uuid)
            vtex_config = project.config.get("vtex_config", {})

            response_data = {
                "results": [],  # Features no longer listed, use agents instead
                "store_type": vtex_config.get("vtex_store_type", ""),
            }

            if nexus_agents:
                # List Nexus agents
                agents_data = self.nexus_service.list_agents(project_uuid)
                if agents_data:
                    response_data["nexus_agents"] = agents_data

                # List gallery agents
                try:
                    gallery_agents = ListAgentsUseCase.execute(project_uuid)
                except Exception as e:
                    gallery_agents = []
                    logger.error(f"Error fetching gallery agents: {e}")

                serializer = GalleryAgentSerializer(
                    gallery_agents, many=True, context={"project_uuid": project_uuid}
                )
                response_data["gallery_agents"] = serializer.data

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
