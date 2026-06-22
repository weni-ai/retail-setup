"""
Shared lookup for agents already integrated in a project.

Combines two sources to build a complete set of integrated agent UUIDs:
  - Nexus API (passive agents toggled via app-assign)
  - Retail DB (active agents assigned via IntegratedAgent)

Used by both IntegrateAgentsUseCase (onboarding flow) and
InstallChannelAgentsUseCase (post-onboarding channel addition)
to skip agents that are already integrated.
"""

from typing import Set

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.services.nexus.service import NexusService


def get_integrated_agent_uuids(
    project_uuid: str, nexus_service: NexusService
) -> Set[str]:
    """Returns the union of Nexus-integrated and Retail-integrated agent UUIDs."""
    return _get_nexus_uuids(project_uuid, nexus_service) | _get_retail_uuids(
        project_uuid
    )


def _get_nexus_uuids(project_uuid: str, nexus_service: NexusService) -> Set[str]:
    """Fetches UUIDs of passive agents integrated via Nexus."""
    response = nexus_service.list_integrated_agents(project_uuid)
    if not response:
        return set()

    agents = response if isinstance(response, list) else response.get("results", [])
    return {str(agent.get("uuid", "")) for agent in agents if agent.get("uuid")}


def _get_retail_uuids(project_uuid: str) -> Set[str]:
    """Fetches UUIDs of active agents integrated via Retail."""
    return {
        str(uuid)
        for uuid in IntegratedAgent.objects.filter(
            project__uuid=project_uuid,
            project__is_active=True,
            is_active=True,
        )
        .values_list("agent__uuid", flat=True)
        .distinct()
    }
