from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Iterable, Optional

from uuid import UUID

from django.conf import settings
from django.core.cache import cache

from retail.agents.domains.agent_integration.models import IntegratedAgent


class AgentRole(str, Enum):
    """Special integration roles that have a project-scoped cache entry.

    Each role maps to a Django setting holding the canonical
    ``Agent.uuid`` for that role. The handler uses this enum (and the
    mapping below) as the single source of truth so every cache layer
    derives its keys consistently.
    """

    ABANDONED_CART = "abandoned_cart"
    ORDER_STATUS = "order_status"
    PAYMENT_RECOVERY = "payment_recovery"


ROLE_SETTING_NAMES: Dict[AgentRole, str] = {
    AgentRole.ABANDONED_CART: "ABANDONED_CART_AGENT_UUID",
    AgentRole.ORDER_STATUS: "ORDER_STATUS_AGENT_UUID",
    AgentRole.PAYMENT_RECOVERY: "PAYMENT_RECOVERY_AGENT_UUID",
}


class IntegratedAgentCacheHandler(ABC):
    """Single source of truth for IntegratedAgent-derived caches.

    Two cache layers are managed here:

    * **Webhook cache** (short TTL): one entry per ``IntegratedAgent.uuid``
      used by the synchronous webhook hot path. Reflects in-flight edits
      (e.g. ``contact_percentage``, ``config``) within seconds.
    * **Role cache** (long TTL): one entry per ``(role, project_uuid)``
      pointing at the ``IntegratedAgent`` that fulfills that role for
      the project. Lookups by role hit Redis instead of the database.

    Use cases must never compose cache keys directly; they should call
    into this handler so future layout changes are a single edit.
    """

    @abstractmethod
    def get_cache_key(self, integrated_agent_uuid: UUID) -> str:
        """Generate a cache key for the integrated agent webhook cache."""

    @abstractmethod
    def get_cached_agent(
        self, integrated_agent_uuid: UUID
    ) -> Optional[IntegratedAgent]:
        """Retrieve the integrated agent from the webhook cache."""

    @abstractmethod
    def set_cached_agent(self, integrated_agent: IntegratedAgent) -> None:
        """Set the integrated agent in the webhook cache."""

    @abstractmethod
    def clear_cached_agent(self, integrated_agent_uuid: UUID) -> None:
        """Clear the integrated agent from the webhook cache."""

    def clear_cached_agents(self, integrated_agent_uuids: Iterable[UUID]) -> None:
        """Clear multiple integrated agents from the webhook cache.

        Default implementation calls ``clear_cached_agent`` per uuid;
        backends that support batch deletion may override this for a
        single round-trip.
        """
        for integrated_agent_uuid in integrated_agent_uuids:
            self.clear_cached_agent(integrated_agent_uuid)

    @abstractmethod
    def get_role_cache_key(self, project_uuid: UUID, role: AgentRole) -> str:
        """Generate a cache key for the role-based project cache."""

    @abstractmethod
    def get_role_agent(
        self, project_uuid: UUID, role: AgentRole
    ) -> Optional[IntegratedAgent]:
        """Retrieve the IntegratedAgent fulfilling ``role`` for ``project``."""

    @abstractmethod
    def set_role_agent(
        self, integrated_agent: IntegratedAgent, role: AgentRole
    ) -> None:
        """Cache ``integrated_agent`` as the holder of ``role`` for its project."""

    @abstractmethod
    def clear_role_agent(self, project_uuid: UUID, role: AgentRole) -> None:
        """Clear the role cache entry for ``(role, project)``."""

    @abstractmethod
    def clear_agent_active_flag(self, vtex_account: str, role: AgentRole) -> None:
        """Clear the boolean cache from ``CheckAgentActiveUseCase``.

        That cache stores ``agent_active_<vtex_account>_<role>`` for 60s
        and is consumed by the public-API endpoint that tells the
        frontend whether a given role is active for a VTEX account.
        Without explicit invalidation, assign/unassign/update would be
        invisible to that endpoint for up to 60s.
        """

    def invalidate_all_for(self, integrated_agent: IntegratedAgent) -> None:
        """Clear every cache key derived from ``integrated_agent``.

        Always clears the webhook cache. Additionally clears the role
        cache entry and the ``CheckAgentActive`` boolean flag for the
        role this agent currently fulfills, if any. Callers don't need
        to know the role; the handler resolves it from settings.
        """
        self.clear_cached_agent(integrated_agent.uuid)
        role = self.resolve_role(integrated_agent)
        if role is None:
            return

        self.clear_role_agent(integrated_agent.project.uuid, role)

        vtex_account = integrated_agent.project.vtex_account
        if vtex_account:
            self.clear_agent_active_flag(vtex_account, role)

    @staticmethod
    def resolve_role(integrated_agent: IntegratedAgent) -> Optional[AgentRole]:
        """Match ``integrated_agent`` against the role settings.

        Returns the matching ``AgentRole`` or ``None`` if the agent does
        not fulfill any of the special roles tracked by this handler.
        """
        agent_uuid = str(integrated_agent.agent.uuid)
        for role, setting_name in ROLE_SETTING_NAMES.items():
            configured = getattr(settings, setting_name, "")
            if configured and configured == agent_uuid:
                return role
        return None


class IntegratedAgentCacheHandlerRedis(IntegratedAgentCacheHandler):
    """Redis-backed implementation using Django's cache framework.

    TTLs are chosen to balance hot-path latency vs. propagation of
    edits:

    * ``WEBHOOK_TTL`` (30s): tight loop with the dispatch path; short
      enough that ``contact_percentage`` and ``config`` edits feel
      almost real-time without explicit invalidation.
    * ``ROLE_TTL`` (6h): role-by-project lookups are stable per project
      and are explicitly invalidated on assign/unassign/update via
      ``invalidate_all_for``.
    """

    WEBHOOK_TTL = 30  # seconds
    ROLE_TTL = 21600  # 6 hours

    def __init__(
        self, cache_key_prefix: Optional[str] = None, cache_time: Optional[int] = None
    ) -> None:
        # The kwargs control the webhook cache only, which is the only
        # one this class managed before the role-cache extension.
        self.cache_key_prefix = cache_key_prefix or "integrated_agent_webhook"
        self.cache_time = cache_time or self.WEBHOOK_TTL

    def get_cache_key(self, integrated_agent_uuid: UUID) -> str:
        return f"{self.cache_key_prefix}_{integrated_agent_uuid}"

    def get_cached_agent(
        self, integrated_agent_uuid: UUID
    ) -> Optional[IntegratedAgent]:
        return cache.get(self.get_cache_key(integrated_agent_uuid))

    def set_cached_agent(self, integrated_agent: IntegratedAgent) -> None:
        cache.set(
            self.get_cache_key(integrated_agent.uuid),
            integrated_agent,
            timeout=self.cache_time,
        )

    def clear_cached_agent(self, integrated_agent_uuid: UUID) -> None:
        cache.delete(self.get_cache_key(integrated_agent_uuid))

    def clear_cached_agents(self, integrated_agent_uuids: Iterable[UUID]) -> None:
        keys = [self.get_cache_key(u) for u in integrated_agent_uuids]
        if keys:
            cache.delete_many(keys)

    def get_role_cache_key(self, project_uuid: UUID, role: AgentRole) -> str:
        return f"{role.value}_agent_{project_uuid}"

    def get_role_agent(
        self, project_uuid: UUID, role: AgentRole
    ) -> Optional[IntegratedAgent]:
        return cache.get(self.get_role_cache_key(project_uuid, role))

    def set_role_agent(
        self, integrated_agent: IntegratedAgent, role: AgentRole
    ) -> None:
        cache.set(
            self.get_role_cache_key(integrated_agent.project.uuid, role),
            integrated_agent,
            timeout=self.ROLE_TTL,
        )

    def clear_role_agent(self, project_uuid: UUID, role: AgentRole) -> None:
        cache.delete(self.get_role_cache_key(project_uuid, role))

    def clear_agent_active_flag(self, vtex_account: str, role: AgentRole) -> None:
        cache.delete(f"agent_active_{vtex_account}_{role.value}")
