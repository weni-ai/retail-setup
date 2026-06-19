import logging
from typing import Iterable

from django.conf import settings
from django.core.cache import cache

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.features.models import IntegratedFeature
from retail.projects.models import Project


logger = logging.getLogger(__name__)

AGENT_UUID_SETTINGS_MAP = {
    "abandoned_cart": "ABANDONED_CART_AGENT_UUID",
    "order_status": "ORDER_STATUS_AGENT_UUID",
    "payment_recovery": "PAYMENT_RECOVERY_AGENT_UUID",
}

CACHE_TIMEOUT = 60


class CheckAgentActiveUseCase:
    """Checks whether a given agent type is active for a VTEX account's project."""

    def execute(self, vtex_account: str, agent_type: str) -> bool:
        cache_key = f"agent_active_{vtex_account}_{agent_type}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        is_active = self._check(vtex_account, agent_type)
        cache.set(cache_key, is_active, timeout=CACHE_TIMEOUT)
        return is_active

    def execute_any(self, vtex_account: str, agent_types: Iterable[str]) -> bool:
        """Return True if at least one of ``agent_types`` is active.

        Each individual check goes through ``execute`` and therefore
        reuses its per-role cache (key ``agent_active_<vtex>_<role>``,
        60s TTL). Iteration short-circuits on the first match, so callers
        should pass the most likely role first to keep the hot path cheap.
        """
        for agent_type in agent_types:
            if self.execute(vtex_account, agent_type):
                return True
        return False

    def _check(self, vtex_account: str, agent_type: str) -> bool:
        project = self._get_project(vtex_account)
        if not project:
            return False

        if self._has_active_integrated_agent(project, agent_type):
            return True

        if self._has_legacy_feature(project, agent_type):
            return True

        return False

    def _get_project(self, vtex_account: str):
        try:
            return Project.objects.get(vtex_account=vtex_account)
        except (Project.DoesNotExist, Project.MultipleObjectsReturned):
            logger.info(f"Project lookup failed for vtex_account={vtex_account}")
            return None

    def _has_active_integrated_agent(self, project: Project, agent_type: str) -> bool:
        """Checks the new agent system (IntegratedAgent)."""
        agent_uuid = self._get_agent_uuid(agent_type)
        if not agent_uuid:
            return False

        if self._has_active_agent(project, agent_uuid):
            return True

        if agent_type == "order_status":
            return self._has_custom_order_status_agent(project)

        return False

    def _get_agent_uuid(self, agent_type: str):
        setting_name = AGENT_UUID_SETTINGS_MAP.get(agent_type)
        if not setting_name:
            return None

        agent_uuid = getattr(settings, setting_name, "")
        if not agent_uuid:
            logger.info(f"{setting_name} is not configured in settings")
            return None

        return agent_uuid

    def _has_active_agent(self, project: Project, agent_uuid: str) -> bool:
        return IntegratedAgent.objects.filter(
            agent__uuid=agent_uuid,
            project=project,
            is_active=True,
        ).exists()

    def _has_custom_order_status_agent(self, project: Project) -> bool:
        """Checks for custom agents that inherit from the official order status agent."""
        return IntegratedAgent.objects.filter(
            parent_agent_uuid__isnull=False,
            project=project,
            is_active=True,
        ).exists()

    def _has_legacy_feature(self, project: Project, agent_type: str) -> bool:
        """Fallback check for legacy IntegratedFeature integration (Feature.code matches agent_type)."""
        return IntegratedFeature.objects.filter(
            project=project,
            feature__code=agent_type,
        ).exists()
