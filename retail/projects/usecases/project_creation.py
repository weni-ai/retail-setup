from retail.projects.models import Project
from retail.projects.usecases.project_dto import ProjectCreationDTO
from django.core.exceptions import MultipleObjectsReturned


class ProjectCreationUseCase:
    @staticmethod
    def create_project(project_dto: ProjectCreationDTO):
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
    def _create_new_project(project_dto: ProjectCreationDTO, include_vtex: bool = False):
        """
        Creates a new project. Optionally includes VTEX account details.
        """
        project_data = {
            "name": project_dto.name,
            "uuid": project_dto.uuid,
            "organization_uuid": project_dto.organization_uuid,
        }

        if include_vtex:
            project_data["vtex_account"] = project_dto.vtex_account

        Project.objects.create(**project_data)

