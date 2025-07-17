from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from retail.services.integrations.service import IntegrationsService
from retail.templates.models import Template
from retail.templates.usecases.template_metrics import FetchTemplateMetricsUseCase


class TestFetchTemplateMetricsUseCase(TestCase):
    """
    Unit tests for FetchTemplateMetricsUseCase.
    Tests both public interface and internal private methods,
    including error handling and integration service behavior.
    """

    def setUp(self):
        self.service_mock = MagicMock(spec=IntegrationsService)
        self.use_case = FetchTemplateMetricsUseCase(service=self.service_mock)
        self.template_uuid = str(uuid4())
        self.version_uuid = str(uuid4())
        self.app_uuid = str(uuid4())
        self.start = "2024-01-01"
        self.end = "2024-01-31"

    def test_execute_success(self):
        """Should fetch metrics successfully when all data exists."""

        mock_template = MagicMock()
        mock_template.uuid = self.template_uuid

        self.use_case._get_template_with_versions = MagicMock(
            return_value=mock_template
        )
        self.use_case._get_version_uuids = MagicMock(return_value=[self.version_uuid])
        self.use_case._get_integrations_app_uuid = MagicMock(return_value=self.app_uuid)

        expected_response = {"metrics": [{"count": 123}]}
        self.service_mock.fetch_template_metrics.return_value = expected_response

        result = self.use_case.execute(self.template_uuid, self.start, self.end)

        self.assertEqual(result, expected_response)
        self.service_mock.fetch_template_metrics.assert_called_once_with(
            app_uuid=self.app_uuid,
            template_versions=[self.version_uuid],
            start=self.start,
            end=self.end,
        )
        self.use_case._get_template_with_versions.assert_called_once_with(
            self.template_uuid
        )
        self.use_case._get_version_uuids.assert_called_once_with(mock_template)
        self.use_case._get_integrations_app_uuid.assert_called_once_with(mock_template)

    def test_template_not_found(self):
        """Should raise ValueError if template does not exist."""
        self.use_case._get_template_with_versions = MagicMock(
            side_effect=ValueError("Template not found.")
        )

        with self.assertRaises(ValueError) as context:
            self.use_case.execute(self.template_uuid, self.start, self.end)
        self.assertEqual(str(context.exception), "Template not found.")

    def test_template_without_versions(self):
        """Should raise ValueError if template has no versions."""
        self.use_case._get_template_with_versions = MagicMock()
        self.use_case._get_version_uuids = MagicMock(
            side_effect=ValueError("No versions found for this template.")
        )
        self.use_case._get_integrations_app_uuid = MagicMock()

        with self.assertRaises(ValueError) as context:
            self.use_case.execute(self.template_uuid, self.start, self.end)
        self.assertEqual(str(context.exception), "No versions found for this template.")

    def test_missing_integrations_app_uuid(self):
        """Should raise ValueError if integrations_app_uuid is missing."""
        self.use_case._get_template_with_versions = MagicMock()
        self.use_case._get_version_uuids = MagicMock(return_value=[self.version_uuid])
        self.use_case._get_integrations_app_uuid = MagicMock(
            side_effect=ValueError(
                "Integrations app UUID is missing in the first version."
            )
        )

        with self.assertRaises(ValueError) as context:
            self.use_case.execute(self.template_uuid, self.start, self.end)
        self.assertEqual(
            str(context.exception),
            "Integrations app UUID is missing in the first version.",
        )

    # ------- Tests for private methods --------
    @patch("retail.templates.usecases.template_metrics.Template")
    def test_get_template_with_versions_success(self, mock_template_model):
        """_get_template_with_versions: should return template when template and versions exist."""

        mock_template = MagicMock()
        mock_template.versions.exists.return_value = True
        mock_template_model.objects.prefetch_related.return_value.get.return_value = (
            mock_template
        )

        result = self.use_case._get_template_with_versions(self.template_uuid)
        self.assertEqual(result, mock_template)
        mock_template.versions.exists.assert_called_once()

    def test_get_template_with_versions_not_found(self):
        """
        Should raise ValueError if template is not found, covering the except block.
        """
        # Step 1: Patch objects to return a mock for prefetch_related
        with patch.object(
            Template.objects, "prefetch_related"
        ) as prefetch_related_mock:
            prefetch_related_result = MagicMock()
            prefetch_related_mock.return_value = prefetch_related_result

            # Step 2: Patch get on the result of prefetch_related
            prefetch_related_result.get.side_effect = Template.DoesNotExist()

            with self.assertRaises(ValueError) as context:
                self.use_case._get_template_with_versions(self.template_uuid)
            self.assertEqual(str(context.exception), "Template not found.")

    @patch("retail.templates.usecases.template_metrics.Template")
    def test_get_template_with_versions_no_versions(self, mock_template_model):
        """_get_template_with_versions: template exists but has no versions."""
        mock_template = MagicMock()
        mock_template.versions.exists.return_value = False
        mock_template_model.objects.prefetch_related.return_value.get.return_value = (
            mock_template
        )

        with self.assertRaises(ValueError) as context:
            self.use_case._get_template_with_versions(self.template_uuid)
        self.assertEqual(str(context.exception), "No versions found for this template.")

    def test_get_version_uuids(self):
        """_get_version_uuids: should return list of version uuids as strings."""
        mock_template = MagicMock()
        mock_version1 = MagicMock()
        mock_version2 = MagicMock()
        mock_version1.uuid = uuid4()
        mock_version2.uuid = uuid4()
        mock_template.versions.all.return_value = [mock_version1, mock_version2]

        uuids = self.use_case._get_version_uuids(mock_template)
        self.assertEqual(uuids, [str(mock_version1.uuid), str(mock_version2.uuid)])

    def test_get_integrations_app_uuid_success(self):
        """_get_integrations_app_uuid: should return the uuid of the integrations app."""
        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_uuid = uuid4()
        mock_version.integrations_app_uuid = mock_uuid
        mock_template.versions.first.return_value = mock_version
        mock_template.uuid = self.template_uuid

        result = self.use_case._get_integrations_app_uuid(mock_template)
        self.assertEqual(result, str(mock_uuid))

    def test_get_integrations_app_uuid_missing(self):
        """_get_integrations_app_uuid: should raise ValueError if no app uuid is found."""
        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_version.integrations_app_uuid = None
        mock_template.versions.first.return_value = mock_version
        mock_template.uuid = self.template_uuid

        with self.assertRaises(ValueError) as context:
            self.use_case._get_integrations_app_uuid(mock_template)
        self.assertEqual(
            str(context.exception),
            "Integrations app UUID is missing in the first version.",
        )

    def test_get_integrations_app_uuid_no_first_version(self):
        """_get_integrations_app_uuid: should raise ValueError if no version exists."""
        mock_template = MagicMock()
        mock_template.versions.first.return_value = None
        mock_template.uuid = self.template_uuid

        with self.assertRaises(ValueError) as context:
            self.use_case._get_integrations_app_uuid(mock_template)
        self.assertEqual(
            str(context.exception),
            "Integrations app UUID is missing in the first version.",
        )
