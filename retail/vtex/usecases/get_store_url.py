import logging

from rest_framework.exceptions import ValidationError

from retail.projects.models import Project

logger = logging.getLogger(__name__)


class GetStoreUrlUseCase:
    """
    Retrieves the store URL (vtex_host_store) from the project config.

    The store URL is set during the onboarding flow when the crawler starts
    and is persisted in the project's config JSON field.
    """

    def execute(self, project_uuid: str) -> dict:
        """
        Looks up the store URL for the given project.

        Args:
            project_uuid: UUID of the project.

        Returns:
            dict with the store_url value.

        Raises:
            ValidationError: If the project does not exist or has no store URL configured.
        """
        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise ValidationError({"detail": "Project not found for given UUID."})

        store_url = project.config.get("vtex_host_store")
        if not store_url:
            raise ValidationError(
                {"detail": "Store URL not found in project configuration."}
            )

        logger.info(f"Store URL retrieved for project_uuid={project_uuid}")
        return {"store_url": store_url}
