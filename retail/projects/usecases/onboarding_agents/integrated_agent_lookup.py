"""
Shared lookup for agents already integrated in a project.

Combines two sources to build a complete set of integrated agent UUIDs:
  - Nexus app-teams API (passive/shared agents toggled via app-assign)
  - Retail DB (active agents assigned via IntegratedAgent)

Used by both IntegrateAgentsUseCase (onboarding flow) and
InstallChannelAgentsUseCase (post-onboarding channel addition)
to skip agents that are already integrated.
"""

from typing import Any, Dict, List, Set

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
    """Fetches UUIDs of agents integrated via Nexus app-assign.

    Uses app-teams (not app-my-agents) because passive/official agents
    belong to another project and only appear in the team integration list.
    """
    response = nexus_service.list_team_agents(project_uuid)
    if not response:
        return set()

    return _extract_uuids_from_team_response(response)


def _extract_uuids_from_team_response(response: Dict[str, Any]) -> Set[str]:
    """Extracts agent UUIDs from app-teams, including inactive integrations.

    app-teams returns every IntegratedAgent for the project (active or not).
    We skip all of them to avoid re-assigning passives that were deliberately
    deactivated; only agents with no Nexus link (e.g. after unassign) are
    integrated again.
    """
    agents: List[Dict[str, Any]] = response.get("agents", [])
    return {str(agent["uuid"]) for agent in agents if agent.get("uuid")}


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
