from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project
from retail.projects.usecases.project_creation import ProjectCreationUseCase
from retail.projects.usecases.project_dto import ProjectCreationDTO


class TestProjectCreationUseCase(TestCase):
    def setUp(self):
        """
        Set up test data for all test methods
        """
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
        """
        Test creating a new project without VTEX account
        """
        ProjectCreationUseCase.create_project(self.base_project_dto)

        created_project = Project.objects.get(uuid=self.base_project_dto.uuid)
        self.assertEqual(created_project.name, self.base_project_dto.name)
        self.assertEqual(
            str(created_project.organization_uuid), self.base_project_dto.organization_uuid
        )
        self.assertIsNone(created_project.vtex_account)

    def test_create_new_project_with_vtex(self):
        """
        Test creating a new project with VTEX account
        """
        ProjectCreationUseCase.create_project(self.vtex_project_dto)

        created_project = Project.objects.get(uuid=self.vtex_project_dto.uuid)
        self.assertEqual(created_project.name, self.vtex_project_dto.name)
        self.assertEqual(
            created_project.vtex_account, self.vtex_project_dto.vtex_account
        )

    def test_update_existing_vtex_project(self):
        """
        Test updating an existing project with new UUID when VTEX account exists
        """
        # Create initial project
        old_uuid = str(uuid4())
        Project.objects.create(
            name="Existing VTEX Project",
            uuid=old_uuid,
            organization_uuid=self.vtex_project_dto.organization_uuid,
            vtex_account=self.vtex_project_dto.vtex_account,
        )

        ProjectCreationUseCase.create_project(self.vtex_project_dto)

        updated_project = Project.objects.get(
            vtex_account=self.vtex_project_dto.vtex_account
        )
        self.assertEqual(str(updated_project.uuid), self.vtex_project_dto.uuid)
        self.assertEqual(Project.objects.count(), 1)

    def test_multiple_vtex_accounts_raises_error(self):
        """
        Test that attempting to create/update a project with duplicate VTEX accounts raises an error
        """
        # Create duplicate projects with same VTEX account
        uuid=str(uuid4())
        for _ in range(2):
            Project.objects.create(
                name="Duplicate VTEX Project",
                uuid=uuid,
                organization_uuid=self.vtex_project_dto.organization_uuid,
                vtex_account=self.vtex_project_dto.vtex_account,
            )

        with self.assertRaises(ValueError) as context:
            ProjectCreationUseCase.create_project(self.vtex_project_dto)

        self.assertEqual(
            str(context.exception),
            f"Multiple projects found for the same VTEX account: {self.vtex_project_dto.vtex_account}",
        )
