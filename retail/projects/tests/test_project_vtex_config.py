from unittest.mock import patch
from django.test import TestCase
from uuid import uuid4

from retail.projects.models import Project
from retail.projects.usecases.project_vtex_config import ProjectVtexConfigUseCase
from retail.projects.usecases.project_dto import ProjectVtexConfigDTO


class TestProjectVtexConfigUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=str(uuid4()), name="Project", vtex_account="", config={}
        )
        self.project_uuid = self.project.uuid

        self.vtex_config_data = ProjectVtexConfigDTO(
            account="testaccount", store_type="site_editor"
        )

        self.invalid_uuid = str(uuid4())

    @patch("retail.projects.usecases.project_vtex_config.logger")
    def test_config_vtex_project_success(self, mock_logger):
        ProjectVtexConfigUseCase.config_vtex_project(
            project_uuid=self.project_uuid, data=self.vtex_config_data
        )

        self.project.refresh_from_db()

        self.assertEqual(self.project.vtex_account, "testaccount")
        self.assertEqual(self.project.config.get("store_type"), "site_editor")

        mock_logger.info.assert_called_with("VTEX project configured successfully")

    @patch("retail.projects.usecases.project_vtex_config.logger")
    def test_config_vtex_project_not_found(self, mock_logger):
        ProjectVtexConfigUseCase.config_vtex_project(
            project_uuid=self.invalid_uuid, data=self.vtex_config_data
        )

        mock_logger.info.assert_called_with(
            f"Project {self.invalid_uuid} not found, skipping config"
        )

    def test_get_project_returns_none_when_not_found(self):
        result = ProjectVtexConfigUseCase._get_project(self.invalid_uuid)
        self.assertIsNone(result)

    def test_get_project_returns_project_when_found(self):
        with patch.object(
            ProjectVtexConfigUseCase, "_get_project", return_value=self.project
        ):
            result = ProjectVtexConfigUseCase._get_project(self.project_uuid)
            self.assertEqual(result, self.project)
