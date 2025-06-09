from unittest.mock import MagicMock, patch

from uuid import uuid4

from django.test import TestCase

from retail.agents.usecases.list_integrated_agents import ListIntegratedAgentUseCase


class ListIntegratedAgentUseCaseTest(TestCase):
    def setUp(self):
        self.usecase = ListIntegratedAgentUseCase()
        self.project_uuid = uuid4()

    @patch("retail.agents.models.IntegratedAgent.objects")
    def test_get_queryset_filters_by_project_and_active(self, mock_objects):
        mock_qs = MagicMock()
        mock_objects.filter.return_value = mock_qs

        result = self.usecase._get_queryset(self.project_uuid)

        mock_objects.filter.assert_called_once_with(
            project__uuid=self.project_uuid, is_active=True
        )
        self.assertEqual(result, mock_qs)

    @patch("retail.agents.models.IntegratedAgent.objects")
    def test_execute_returns_queryset(self, mock_objects):
        mock_qs = MagicMock()
        mock_objects.filter.return_value = mock_qs

        result = self.usecase.execute(self.project_uuid)

        mock_objects.filter.assert_called_once_with(
            project__uuid=self.project_uuid, is_active=True
        )
        self.assertEqual(result, mock_qs)
