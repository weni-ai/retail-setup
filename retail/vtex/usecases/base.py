from abc import ABC
from typing import Tuple

from django.core.cache import cache
from retail.projects.models import Project

VTEX_CONTEXT_CACHE_TTL = 43200  # 12 hours


class BaseVtexUseCase(ABC):
    """
    Abstract base class for VTEX IO use cases.
    Provides common utilities such as domain and account resolution from project UUID.
    """

    def _get_vtex_context(self, project_uuid: str) -> Tuple[str, str]:
        """
        Retrieves VTEX account and domain for a project (single DB hit, cached).

        Returns:
            Tuple of (vtex_account, account_domain).
        """
        cache_key = f"project_vtex_context_{project_uuid}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise ValueError("Project not found for given UUID.")

        if not project.vtex_account:
            raise ValueError("VTEX account not defined for project.")

        vtex_account = project.vtex_account
        domain = f"{vtex_account}.myvtex.com"
        result = (vtex_account, domain)
        cache.set(cache_key, result, timeout=VTEX_CONTEXT_CACHE_TTL)
        return result

    def _get_account_domain(self, project_uuid: str) -> str:
        """Shortcut that returns only the domain."""
        _account, domain = self._get_vtex_context(project_uuid)
        return domain
