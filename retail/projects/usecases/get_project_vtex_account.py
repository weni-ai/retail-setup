from typing import Optional

from retail.projects.models import Project


class GetProjectVtexAccountUseCase:
    """Look up the VTEX account for a project UUID (JWT / internal callers).

    Delegates to ``Project.resolve_vtex_account`` so live desk copilots
    return the parent project's account instead of their empty local field.
    """

    def execute(self, project_uuid: str) -> Optional[str]:
        try:
            project = Project.objects.get(uuid=project_uuid)
            return project.resolve_vtex_account()
        except Project.DoesNotExist:
            return None
