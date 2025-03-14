from retail.projects.models import Project
from rest_framework.exceptions import ValidationError


class ProjectVtexConfigUseCase:
    """Handles VTEX-related configuration within a project."""

    @staticmethod
    def set_store_type(project_uuid: str, vtex_store_type: str) -> dict:
        """Adds or updates the VTEX store type in the project config."""
        if not vtex_store_type:
            raise ValidationError({"error": "vtex_store_type is required"})

        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise ValidationError({"error": "Project not found"})

        # Ensure the VTEX config structure exists
        if "vtex_config" not in project.config:
            project.config["vtex_config"] = {}

        # Add or update the VTEX store type
        project.config["vtex_config"]["vtex_store_type"] = vtex_store_type
        project.save()

        return {"status": "vtex_store_type set"}

    @staticmethod
    def remove_vtex_config(project_uuid: str) -> dict:
        """Removes all VTEX-related configurations from the project config."""
        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise ValidationError({"error": "Project not found"})

        # Remove the entire vtex_config dictionary if it exists
        if "vtex_config" in project.config:
            del project.config["vtex_config"]
            project.save()

        return {"status": "vtex_config removed"}
