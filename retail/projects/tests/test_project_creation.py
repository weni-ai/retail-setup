from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project
from retail.projects.usecases.project_creation import (
    ProjectCreationUseCase,
    VtexAccountConflictError,
)
from retail.projects.usecases.project_dto import ProjectCreationDTO


class TestProjectCreationUseCase(TestCase):
    def setUp(self):
        self.base_project_dto = ProjectCreationDTO(
            name="Test Project",
            uuid="123e4567-e89b-12d3-a456-426614174000",
            organization_uuid=str(uuid4()),
            vtex_account=None,
        )

        self.vtex_project_dto = ProjectCreationDTO(
            name="VTEX Project",
            uuid="123e4567-e89b-12d3-a456-426614174001",
            organization_uuid=str(uuid4()),
            vtex_account="mystore",
        )

    def test_create_new_project_without_vtex(self):
        ProjectCreationUseCase.create_project(self.base_project_dto)

        created_project = Project.objects.get(uuid=self.base_project_dto.uuid)
        self.assertEqual(created_project.name, self.base_project_dto.name)
        self.assertEqual(
            str(created_project.organization_uuid),
            self.base_project_dto.organization_uuid,
        )
        self.assertIsNone(created_project.vtex_account)

    def test_create_new_project_with_vtex(self):
        ProjectCreationUseCase.create_project(self.vtex_project_dto)

        created_project = Project.objects.get(uuid=self.vtex_project_dto.uuid)
        self.assertEqual(created_project.name, self.vtex_project_dto.name)
        self.assertEqual(
            created_project.vtex_account, self.vtex_project_dto.vtex_account
        )

    def test_raises_conflict_when_vtex_account_already_taken(self):
        """A new project with a vtex_account already assigned to another project
        should raise VtexAccountConflictError with both UUIDs in the message."""
        existing_uuid = str(uuid4())
        Project.objects.create(
            name="Existing Project",
            uuid=existing_uuid,
            organization_uuid=str(uuid4()),
            vtex_account=self.vtex_project_dto.vtex_account,
        )

        with self.assertRaises(VtexAccountConflictError) as ctx:
            ProjectCreationUseCase.create_project(self.vtex_project_dto)

        error_msg = str(ctx.exception)
        self.assertIn(self.vtex_project_dto.uuid, error_msg)
        self.assertIn(existing_uuid, error_msg)
        self.assertIn(self.vtex_project_dto.vtex_account, error_msg)
        self.assertIn("Project.objects.create(", error_msg)

    def test_allows_creation_when_vtex_account_owned_by_inactive_project(self):
        """Soft-deleted projects should not block new creations for the same vtex_account."""
        inactive_uuid = str(uuid4())
        Project.all_objects.create(
            name="Inactive Project",
            uuid=inactive_uuid,
            organization_uuid=str(uuid4()),
            vtex_account=self.vtex_project_dto.vtex_account,
            is_active=False,
        )

        ProjectCreationUseCase.create_project(self.vtex_project_dto)

        created_project = Project.objects.get(uuid=self.vtex_project_dto.uuid)
        self.assertEqual(
            created_project.vtex_account, self.vtex_project_dto.vtex_account
        )
        self.assertTrue(created_project.is_active)

    def test_updates_inactive_project_without_reactivating(self):
        """A creation event for a soft-deleted UUID should update fields only."""
        project_uuid = str(uuid4())
        Project.all_objects.create(
            name="Old Name",
            uuid=project_uuid,
            organization_uuid=str(uuid4()),
            vtex_account="mystore",
            is_active=False,
        )

        dto = ProjectCreationDTO(
            name="Updated Name",
            uuid=project_uuid,
            organization_uuid=str(uuid4()),
            vtex_account="mystore",
            language="pt-br",
        )
        ProjectCreationUseCase.create_project(dto)

        project = Project.all_objects.get(uuid=project_uuid)
        self.assertFalse(project.is_active)
        self.assertEqual(project.name, "Updated Name")
        self.assertEqual(project.language, "pt-br")
        self.assertFalse(Project.objects.filter(uuid=project_uuid).exists())

    def test_inactive_project_update_allows_vtex_account_held_by_active_project(
        self,
    ):
        """Inactive projects do not compete for active vtex_account slots."""
        inactive_uuid = str(uuid4())
        vtex_account = "mystore"

        Project.all_objects.create(
            name="Inactive Project",
            uuid=inactive_uuid,
            organization_uuid=str(uuid4()),
            vtex_account=vtex_account,
            is_active=False,
        )
        Project.objects.create(
            name="Active Replacement",
            uuid=str(uuid4()),
            organization_uuid=str(uuid4()),
            vtex_account=vtex_account,
        )

        dto = ProjectCreationDTO(
            name="Updated Inactive Name",
            uuid=inactive_uuid,
            organization_uuid=str(uuid4()),
            vtex_account=vtex_account,
        )
        ProjectCreationUseCase.create_project(dto)

        inactive_project = Project.all_objects.get(uuid=inactive_uuid)
        self.assertFalse(inactive_project.is_active)
        self.assertEqual(inactive_project.name, "Updated Inactive Name")

    def test_active_project_update_raises_conflict_when_vtex_account_taken(self):
        """Active projects must not claim a vtex_account held by another active project."""
        project_uuid = str(uuid4())
        other_uuid = str(uuid4())
        vtex_account = "mystore"

        Project.objects.create(
            name="Existing Project",
            uuid=project_uuid,
            organization_uuid=str(uuid4()),
            vtex_account="other-store",
        )
        Project.objects.create(
            name="Other Active Project",
            uuid=other_uuid,
            organization_uuid=str(uuid4()),
            vtex_account=vtex_account,
        )

        dto = ProjectCreationDTO(
            name="Updated Name",
            uuid=project_uuid,
            organization_uuid=str(uuid4()),
            vtex_account=vtex_account,
        )

        with self.assertRaises(VtexAccountConflictError) as ctx:
            ProjectCreationUseCase.create_project(dto)

        self.assertIn(other_uuid, str(ctx.exception))
        project = Project.objects.get(uuid=project_uuid)
        self.assertEqual(project.vtex_account, "other-store")

    def test_active_project_update_with_same_vtex_account_succeeds(self):
        """Updating an active project with its own vtex_account must not conflict."""
        project_uuid = str(uuid4())
        vtex_account = "mystore"

        Project.objects.create(
            name="Existing Project",
            uuid=project_uuid,
            organization_uuid=str(uuid4()),
            vtex_account=vtex_account,
        )

        dto = ProjectCreationDTO(
            name="Updated Name",
            uuid=project_uuid,
            organization_uuid=str(uuid4()),
            vtex_account=vtex_account,
        )
        ProjectCreationUseCase.create_project(dto)

        project = Project.objects.get(uuid=project_uuid)
        self.assertEqual(project.name, "Updated Name")
        self.assertEqual(project.vtex_account, vtex_account)

    def test_conflict_does_not_modify_existing_project(self):
        """The existing project should remain untouched when a conflict occurs."""
        existing_uuid = str(uuid4())
        Project.objects.create(
            name="Existing Project",
            uuid=existing_uuid,
            organization_uuid=str(uuid4()),
            vtex_account=self.vtex_project_dto.vtex_account,
        )

        with self.assertRaises(VtexAccountConflictError):
            ProjectCreationUseCase.create_project(self.vtex_project_dto)

        self.assertEqual(Project.objects.count(), 1)
        project = Project.objects.get(uuid=existing_uuid)
        self.assertEqual(project.name, "Existing Project")

    def test_update_existing_project_by_uuid(self):
        """When a project with the same UUID exists, update its fields."""
        project_uuid = str(uuid4())
        Project.objects.create(
            name="Old Name",
            uuid=project_uuid,
            organization_uuid=str(uuid4()),
        )

        dto = ProjectCreationDTO(
            name="New Name",
            uuid=project_uuid,
            organization_uuid=str(uuid4()),
            language="en-us",
        )
        ProjectCreationUseCase.create_project(dto)

        project = Project.objects.get(uuid=project_uuid)
        self.assertEqual(project.name, "New Name")
        self.assertEqual(project.language, "en-us")

    def test_create_project_with_language(self):
        dto = ProjectCreationDTO(
            name="Lang Project",
            uuid=str(uuid4()),
            organization_uuid=str(uuid4()),
            vtex_account="langstore",
            language="pt-br",
        )
        ProjectCreationUseCase.create_project(dto)

        project = Project.objects.get(uuid=dto.uuid)
        self.assertEqual(project.language, "pt-br")

    def test_multiple_vtex_accounts_raises_conflict(self):
        for i in range(2):
            Project.objects.create(
                name=f"Duplicate VTEX Project {i+1}",
                uuid=str(uuid4()),
                organization_uuid=self.vtex_project_dto.organization_uuid,
                vtex_account=self.vtex_project_dto.vtex_account,
            )

        with self.assertRaises(VtexAccountConflictError) as ctx:
            ProjectCreationUseCase.create_project(self.vtex_project_dto)

        self.assertIn(self.vtex_project_dto.vtex_account, str(ctx.exception))
