import logging

from django.core.exceptions import MultipleObjectsReturned
from django.db import IntegrityError

from retail.projects.models import Project
from retail.projects.usecases.project_dto import ProjectCreationDTO

logger = logging.getLogger(__name__)


class VtexAccountConflictError(Exception):
    """Raised when trying to create a project with a vtex_account already in use."""


class ProjectCreationUseCase:
    @staticmethod
    def create_project(project_dto: ProjectCreationDTO):
        """
        Creates or updates a project. Handles duplicate UUIDs gracefully.

        Raises:
            VtexAccountConflictError: If the vtex_account is already assigned
                to a different project (stale record that was not deleted).
        """
        try:
            existing_project = Project.objects.get(uuid=project_dto.uuid)
            logger.info(f"Project {project_dto.uuid} already exists, updating fields")
            existing_project.name = project_dto.name
            existing_project.organization_uuid = project_dto.organization_uuid
            if project_dto.vtex_account:
                existing_project.vtex_account = project_dto.vtex_account
            if project_dto.language:
                existing_project.language = project_dto.language
            existing_project.save()
            return existing_project
        except Project.DoesNotExist:
            logger.info(
                f"Project {project_dto.uuid} not found, "
                f"proceeding with creation "
                f"(vtex_account={project_dto.vtex_account})"
            )
            if project_dto.vtex_account:
                ProjectCreationUseCase._check_vtex_account_conflict(project_dto)
            return ProjectCreationUseCase._create_new_project(
                project_dto, include_vtex=bool(project_dto.vtex_account)
            )

    @staticmethod
    def _check_vtex_account_conflict(project_dto: ProjectCreationDTO) -> None:
        """
        Ensures no other project already holds this vtex_account.

        If the delete event from Connect was missed, a stale project may still
        own the vtex_account. Instead of silently overwriting it, we surface
        the conflict so it can be investigated.
        """
        try:
            existing = Project.objects.get(vtex_account=project_dto.vtex_account)
        except Project.DoesNotExist:
            return
        except MultipleObjectsReturned:
            raise VtexAccountConflictError(
                f"Multiple projects found for vtex_account={project_dto.vtex_account}"
            )

        create_kwargs = (
            f'name="{project_dto.name}", '
            f'uuid="{project_dto.uuid}", '
            f'organization_uuid="{project_dto.organization_uuid}", '
            f'vtex_account="{project_dto.vtex_account}"'
        )
        if project_dto.language:
            create_kwargs += f', language="{project_dto.language}"'

        raise VtexAccountConflictError(
            f"Cannot create project {project_dto.uuid} for "
            f"vtex_account={project_dto.vtex_account}: "
            f"already assigned to existing project {existing.uuid}. "
            f"The existing project may be stale and needs deletion. "
            f"To resolve manually, delete the stale project and run: "
            f"Project.objects.create({create_kwargs})"
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

        if project_dto.language:
            project_data["language"] = project_dto.language

        try:
            project, created = Project.objects.get_or_create(
                uuid=project_dto.uuid, defaults=project_data
            )
            if not created:
                for key, value in project_data.items():
                    setattr(project, key, value)
                project.save()
            return project
        except IntegrityError:
            try:
                return Project.objects.get(uuid=project_dto.uuid)
            except Project.DoesNotExist:
                raise
