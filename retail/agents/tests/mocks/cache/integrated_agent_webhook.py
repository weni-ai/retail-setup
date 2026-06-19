from typing import Optional

from uuid import UUID

from retail.agents.shared.cache import AgentRole, IntegratedAgentCacheHandler
from retail.agents.domains.agent_integration.models import IntegratedAgent


class IntegratedAgentCacheHandlerMock(IntegratedAgentCacheHandler):
    """In-memory mock used by tests that exercise the cache contract.

    Backed by a single ``dict`` keyed by the same string keys the
    Redis implementation would write, so assertions work for both
    the webhook cache and the role cache.
    """

    def __init__(self) -> None:
        self.cache = {}

    def get_cache_key(self, integrated_agent_uuid: UUID) -> str:
        return str(integrated_agent_uuid)

    def get_cached_agent(
        self, integrated_agent_uuid: UUID
    ) -> Optional[IntegratedAgent]:
        return self.cache.get(self.get_cache_key(integrated_agent_uuid))

    def set_cached_agent(self, integrated_agent: IntegratedAgent) -> None:
        self.cache[self.get_cache_key(integrated_agent.uuid)] = integrated_agent

    def clear_cached_agent(self, integrated_agent_uuid: UUID) -> None:
        self.cache.pop(self.get_cache_key(integrated_agent_uuid), None)

    def get_role_cache_key(self, project_uuid: UUID, role: AgentRole) -> str:
        return f"{role.value}_agent_{project_uuid}"

    def get_role_agent(
        self, project_uuid: UUID, role: AgentRole
    ) -> Optional[IntegratedAgent]:
        return self.cache.get(self.get_role_cache_key(project_uuid, role))

    def set_role_agent(
        self, integrated_agent: IntegratedAgent, role: AgentRole
    ) -> None:
        key = self.get_role_cache_key(integrated_agent.project.uuid, role)
        self.cache[key] = integrated_agent

    def clear_role_agent(self, project_uuid: UUID, role: AgentRole) -> None:
        self.cache.pop(self.get_role_cache_key(project_uuid, role), None)

    def clear_agent_active_flag(self, vtex_account: str, role: AgentRole) -> None:
        # No-op for in-memory tests; the real handler delegates to Redis,
        # which is exercised by IntegratedAgentCacheHandlerRedis tests.
        return None
