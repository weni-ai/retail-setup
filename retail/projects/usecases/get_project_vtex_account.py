from typing import Optional

from retail.projects.models import Project


class GetProjectVtexAccountUseCase:
    """Use case for retrieving the VTEX account associated with a project."""

    def execute(self, project_uuid: str) -> Optional[str]:
        """
        Execute the use case to get the VTEX account for a given project UUID.

        Args:
            project_uuid (str): The UUID of the project.

        Returns:
            Optional[str]: The VTEX account if found, otherwise None.
        """
        try:
            project = Project.objects.get(uuid=project_uuid)
            if not project.vtex_account:  # covers None and ""
                return None
            return project.vtex_account
        except Project.DoesNotExist:
            return None
