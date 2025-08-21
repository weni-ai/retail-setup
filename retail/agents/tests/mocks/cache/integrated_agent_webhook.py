from typing import Optional

from uuid import UUID

from retail.agents.shared.cache import IntegratedAgentCacheHandler
from retail.agents.domains.agent_integration.models import IntegratedAgent


class IntegratedAgentCacheHandlerMock(IntegratedAgentCacheHandler):
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
