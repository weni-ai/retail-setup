from abc import ABC
from django.core.cache import cache
from retail.projects.models import Project


class BaseVtexUseCase(ABC):
    """
    Abstract base class for VTEX IO use cases.
    Provides common utilities such as domain resolution from project UUID.
    """

    def _get_account_domain(self, project_uuid: str) -> str:
        """
        Retrieves the VTEX account domain associated with a project, with caching.

        Args:
            project_uuid (str): UUID of the project.

        Returns:
            str: The VTEX account domain (e.g., 'account.myvtex.com').

        Raises:
            ValueError: If the project does not exist or lacks a VTEX account.
        """
        cache_key = f"project_domain_{project_uuid}"
        cached_domain = cache.get(cache_key)

        if cached_domain:
            return cached_domain

        try:
            project = Project.objects.get(uuid=project_uuid)
            if not project.vtex_account:
                raise ValueError("VTEX account not defined for project.")

            domain = f"{project.vtex_account}.myvtex.com"
            cache.set(cache_key, domain, timeout=43200)  # 12 hours
            return domain
        except Project.DoesNotExist:
            raise ValueError("Project not found for given UUID.")
