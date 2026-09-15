import logging
from typing import Optional

from django.core.exceptions import MultipleObjectsReturned
from django.db import IntegrityError

from retail.projects.models import Project
from retail.projects.usecases.project_dto import ProjectCreationDTO

logger = logging.getLogger(__name__)


class VtexAccountConflictError(Exception):
    """Raised when trying to create a project with a vtex_account already in use."""


class ParentProjectNotFoundError(Exception):
    """Raised when a copilot event references a parent project that is not stored yet."""


class ProjectCreationUseCase:
    @staticmethod
    def create_project(project_dto: ProjectCreationDTO):
        """
        Creates or updates a project. Handles duplicate UUIDs gracefully.

        Raises:
            VtexAccountConflictError: If the vtex_account is already assigned
                to a different active project (stale record that was not
                soft-deleted).
            ParentProjectNotFoundError: If the event is a live desk copilot
                and the parent project is missing locally.
        """
        parent_project = ProjectCreationUseCase._resolve_parent_project(project_dto)

        try:
            existing_project = Project.all_objects.get(uuid=project_dto.uuid)
            return ProjectCreationUseCase._update_existing_project(
                existing_project,
                project_dto,
                parent_project=parent_project,
            )
        except Project.DoesNotExist:
            logger.info(
                f"Project {project_dto.uuid} not found, "
                f"proceeding with creation "
                f"(vtex_account={project_dto.vtex_account}, "
                f"is_live_desk_copilot={project_dto.is_live_desk_copilot})"
            )
            if ProjectCreationUseCase._should_persist_vtex_account(project_dto):
                ProjectCreationUseCase._check_vtex_account_conflict(project_dto)
            return ProjectCreationUseCase._create_new_project(
                project_dto,
                parent_project=parent_project,
            )

    @staticmethod
    def _should_persist_vtex_account(project_dto: ProjectCreationDTO) -> bool:
        """Return whether this event may write ``vtex_account`` on the project row.

        Copilots inherit the parent's account and must not store their own,
        even when the EDA payload repeats the parent account.
        """
        return bool(project_dto.vtex_account) and not project_dto.is_live_desk_copilot

    @staticmethod
    def _resolve_parent_project(project_dto: ProjectCreationDTO) -> Optional[Project]:
        """Return the parent project for a live desk copilot event, or ``None``.

        Non-copilot events skip the lookup. Copilots must include
        ``parent_project_uuid``; the parent is loaded via ``all_objects`` so a
        soft-deleted parent still satisfies the FK.

        Raises:
            ParentProjectNotFoundError: Missing parent UUID, or no local row
                yet (consumer should nack and retry).
        """
        if not project_dto.is_live_desk_copilot:
            return None
        if not project_dto.parent_project_uuid:
            raise ParentProjectNotFoundError(
                f"Copilot project {project_dto.uuid} is missing parent_project_uuid"
            )
        try:
            return Project.all_objects.get(uuid=project_dto.parent_project_uuid)
        except Project.DoesNotExist:
            raise ParentProjectNotFoundError(
                f"Parent project {project_dto.parent_project_uuid} not found "
                f"for copilot {project_dto.uuid}"
            )

    @staticmethod
    def _update_existing_project(
        existing_project: Project,
        project_dto: ProjectCreationDTO,
        parent_project: Optional[Project] = None,
    ) -> Project:
        """Apply the event fields onto an existing row (including inactive ones).

        Inactive projects skip the vtex_account uniqueness check. Copilot
        updates clear any leftover local account so the parent stays the
        source of truth.
        """
        persist_vtex = ProjectCreationUseCase._should_persist_vtex_account(project_dto)
        if not existing_project.is_active:
            logger.warning(
                f"Updating inactive project {project_dto.uuid} "
                f"(vtex_account={existing_project.vtex_account})"
            )
        elif persist_vtex:
            ProjectCreationUseCase._check_vtex_account_conflict(project_dto)

        logger.info(f"Project {project_dto.uuid} already exists, updating fields")
        existing_project.name = project_dto.name
        existing_project.organization_uuid = project_dto.organization_uuid
        if persist_vtex:
            existing_project.vtex_account = project_dto.vtex_account
        elif project_dto.is_live_desk_copilot:
            existing_project.vtex_account = None
        if project_dto.language:
            existing_project.language = project_dto.language
        existing_project.is_live_desk_copilot = project_dto.is_live_desk_copilot
        existing_project.parent_project = parent_project
        existing_project.save()
        return existing_project

    @staticmethod
    def _check_vtex_account_conflict(project_dto: ProjectCreationDTO) -> None:
        """
        Ensures no other active project already holds this vtex_account.

        If the delete event from Connect was missed, a stale active project may
        still own the vtex_account. Instead of silently overwriting it, we
        surface the conflict so it can be investigated.
        """
        try:
            existing = Project.objects.get(vtex_account=project_dto.vtex_account)
        except Project.DoesNotExist:
            return
        except MultipleObjectsReturned:
            raise VtexAccountConflictError(
                f"Multiple active projects found for "
                f"vtex_account={project_dto.vtex_account}"
            )

        if str(existing.uuid) == str(project_dto.uuid):
            return

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
            f"already assigned to existing active project {existing.uuid}. "
            f"The existing project may be stale and needs soft deletion. "
            f"To resolve manually, run: "
            f"Project.all_objects.filter(uuid='{existing.uuid}')"
            f".update(is_active=False) then "
            f"Project.objects.create({create_kwargs})"
        )

    @staticmethod
    def _create_new_project(
        project_dto: ProjectCreationDTO,
        parent_project: Optional[Project] = None,
    ):
        """Insert a project row, omitting ``vtex_account`` for copilots.

        Uses get_or_create (and IntegrityError fallback) to absorb a concurrent
        duplicate of the same UUID.
        """
        project_data = {
            "name": project_dto.name,
            "uuid": project_dto.uuid,
            "organization_uuid": project_dto.organization_uuid,
            "is_live_desk_copilot": project_dto.is_live_desk_copilot,
            "parent_project": parent_project,
        }

        if ProjectCreationUseCase._should_persist_vtex_account(project_dto):
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
                return Project.all_objects.get(uuid=project_dto.uuid)
            except Project.DoesNotExist:
                raise
