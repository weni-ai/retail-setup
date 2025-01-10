from retail.projects.models import Project
from retail.projects.usecases.project_dto import ProjectCreationDTO


class ProjectCreationUseCase:
    @staticmethod
    def create_project(project_dto: ProjectCreationDTO):
        Project.objects.create(
            name=project_dto.name,
            uuid=project_dto.uuid,
            organization_uuid=project_dto.organization_uuid,
            vtex_account=project_dto.vtex_account
        )
