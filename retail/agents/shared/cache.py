from abc import ABC, abstractmethod

from typing import Optional

from uuid import UUID

from django.core.cache import cache

from retail.agents.domains.agent_integration.models import IntegratedAgent


class IntegratedAgentCacheHandler(ABC):
    @abstractmethod
    def get_cache_key(self, integrated_agent_uuid: UUID) -> str:
        """Generate a cache key for the integrated agent."""
        pass

    @abstractmethod
    def get_cached_agent(
        self, integrated_agent_uuid: UUID
    ) -> Optional[IntegratedAgent]:
        """Retrieve the integrated agent from cache."""
        pass

    @abstractmethod
    def set_cached_agent(self, integrated_agent: IntegratedAgent) -> None:
        """Set the integrated agent in cache."""
        pass

    @abstractmethod
    def clear_cached_agent(self, integrated_agent_uuid: UUID) -> None:
        """Clear the integrated agent from cache."""
        pass


class IntegratedAgentCacheHandlerRedis(IntegratedAgentCacheHandler):
    def __init__(
        self, cache_key_prefix: Optional[str] = None, cache_time: Optional[int] = None
    ) -> None:
        self.cache_key_prefix = cache_key_prefix or "integrated_agent_webhook"
        self.cache_time = cache_time or 30

    def get_cache_key(self, integrated_agent_uuid: UUID) -> str:
        return f"{self.cache_key_prefix}_{integrated_agent_uuid}"

    def get_cached_agent(
        self, integrated_agent_uuid: UUID
    ) -> Optional[IntegratedAgent]:
        cache_key = self.get_cache_key(integrated_agent_uuid)
        return cache.get(cache_key)

    def set_cached_agent(self, integrated_agent: IntegratedAgent) -> None:
        cache_key = self.get_cache_key(integrated_agent.uuid)
        cache.set(cache_key, integrated_agent, timeout=self.cache_time)

    def clear_cached_agent(self, integrated_agent_uuid: UUID) -> None:
        print(f"Clearing cache for key: {self.get_cache_key(integrated_agent_uuid)}")
        cache_key = self.get_cache_key(integrated_agent_uuid)
        cache.delete(cache_key)
