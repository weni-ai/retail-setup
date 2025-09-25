from retail.projects.models import Project
from retail.projects.usecases.project_dto import ProjectCreationDTO
from django.core.exceptions import MultipleObjectsReturned
from django.db import IntegrityError


class ProjectCreationUseCase:
    @staticmethod
    def create_project(project_dto: ProjectCreationDTO):
        """
        Creates or updates a project. Handles duplicate UUIDs gracefully.
        """
        # First check if project with this UUID already exists
        try:
            existing_project = Project.objects.get(uuid=project_dto.uuid)
            # Update existing project instead of creating duplicate
            existing_project.name = project_dto.name
            existing_project.organization_uuid = project_dto.organization_uuid
            if project_dto.vtex_account:
                existing_project.vtex_account = project_dto.vtex_account
            existing_project.save()
            return existing_project
        except Project.DoesNotExist:
            # Project doesn't exist, proceed with creation logic
            if project_dto.vtex_account:
                ProjectCreationUseCase._handle_vtex_account_project(project_dto)
            else:
                ProjectCreationUseCase._create_new_project(project_dto)

    @staticmethod
    def _handle_vtex_account_project(project_dto: ProjectCreationDTO):
        """
        Handles the creation or update of a project based on the VTEX account.
        """
        try:
            project = Project.objects.get(vtex_account=project_dto.vtex_account)
            project.uuid = project_dto.uuid
            project.save()
        except Project.DoesNotExist:
            ProjectCreationUseCase._create_new_project(project_dto, include_vtex=True)
        except MultipleObjectsReturned:
            raise ValueError(
                f"Multiple projects found for the same VTEX account: {project_dto.vtex_account}"
            )

    @staticmethod
    def _create_new_project(
        project_dto: ProjectCreationDTO, include_vtex: bool = False
    ):
        """
        Creates a new project. Optionally includes VTEX account details.
        Uses get_or_create to prevent duplicates.
        """
        project_data = {
            "name": project_dto.name,
            "uuid": project_dto.uuid,
            "organization_uuid": project_dto.organization_uuid,
        }

        if include_vtex:
            project_data["vtex_account"] = project_dto.vtex_account

        try:
            project, created = Project.objects.get_or_create(
                uuid=project_dto.uuid, defaults=project_data
            )
            if not created:
                # Project already exists, update it
                for key, value in project_data.items():
                    setattr(project, key, value)
                project.save()
            return project
        except IntegrityError:
            # Handle race condition where project was created between get_or_create calls
            try:
                return Project.objects.get(uuid=project_dto.uuid)
            except Project.DoesNotExist:
                raise
