from unittest.mock import patch, MagicMock
from django.test import TestCase

from retail.templates.models import Template
from retail.templates.usecases.create_library_template import (
    CreateLibraryTemplateUseCase,
)
from retail.templates.usecases._base_library_template import LibraryTemplateData


class TestCreateLibraryTemplateUseCase(TestCase):
    def setUp(self):
        self.use_case = CreateLibraryTemplateUseCase()
        self.payload = LibraryTemplateData(
            library_template_name="Test Library Template", integrated_agent="test_agent"
        )

    @patch.object(CreateLibraryTemplateUseCase, "build_template_and_version")
    def test_execute_success(self, mock_build_template_and_version):
        mock_template = MagicMock(spec=Template)
        mock_version = MagicMock()
        mock_build_template_and_version.return_value = (mock_template, mock_version)

        result = self.use_case.execute(self.payload)

        self.assertEqual(result, (mock_template, mock_version))
        mock_build_template_and_version.assert_called_once_with(
            self.payload, integrated_agent="test_agent"
        )
        self.assertEqual(self.payload["template_name"], "Test Library Template")

    @patch.object(CreateLibraryTemplateUseCase, "build_template_and_version")
    def test_execute_without_integrated_agent(self, mock_build_template_and_version):
        payload_without_agent = LibraryTemplateData(
            library_template_name="Test Library Template"
        )
        mock_template = MagicMock(spec=Template)
        mock_version = MagicMock()
        mock_build_template_and_version.return_value = (mock_template, mock_version)

        result = self.use_case.execute(payload_without_agent)

        self.assertEqual(result, (mock_template, mock_version))
        mock_build_template_and_version.assert_called_once_with(
            payload_without_agent, integrated_agent=None
        )
        self.assertEqual(
            payload_without_agent["template_name"], "Test Library Template"
        )

    @patch.object(CreateLibraryTemplateUseCase, "build_template_and_version")
    def test_execute_sets_template_name_from_library_template_name(
        self, mock_build_template_and_version
    ):
        payload = LibraryTemplateData(
            library_template_name="Custom Library Name", integrated_agent="test_agent"
        )
        mock_template = MagicMock(spec=Template)
        mock_version = MagicMock()
        mock_build_template_and_version.return_value = (mock_template, mock_version)

        self.use_case.execute(payload)

        self.assertEqual(payload["template_name"], "Custom Library Name")
        mock_build_template_and_version.assert_called_once_with(
            payload, integrated_agent="test_agent"
        )

    @patch.object(CreateLibraryTemplateUseCase, "build_template_and_version")
    def test_execute_removes_integrated_agent_from_payload(
        self, mock_build_template_and_version
    ):
        payload = LibraryTemplateData(
            library_template_name="Test Library Template", integrated_agent="test_agent"
        )
        mock_template = MagicMock(spec=Template)
        mock_version = MagicMock()
        mock_build_template_and_version.return_value = (mock_template, mock_version)

        self.use_case.execute(payload)

        self.assertNotIn("integrated_agent", payload)
        mock_build_template_and_version.assert_called_once_with(
            payload, integrated_agent="test_agent"
        )
