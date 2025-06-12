from unittest.mock import patch, MagicMock
from django.test import TestCase
from uuid import uuid4

from retail.agents.models import Agent
from retail.agents.tasks import validate_pre_approved_templates
from retail.projects.models import Project


class ValidatePreApprovedTemplatesTaskTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Test Project", uuid=uuid4())

        self.agent1 = Agent.objects.create(
            uuid=uuid4(),
            name="Test Agent 1",
            slug="test-agent-1",
            description="Test agent description",
            project=self.project,
        )

        self.agent2 = Agent.objects.create(
            uuid=uuid4(),
            name="Test Agent 2",
            slug="test-agent-2",
            description="Test agent description",
            project=self.project,
        )

    @patch("retail.agents.tasks.ValidatePreApprovedTemplatesUseCase")
    def test_validate_pre_approved_templates_success(self, mock_use_case_class):
        mock_use_case = MagicMock()
        mock_use_case_class.return_value = mock_use_case

        agents_ids = [str(self.agent1.uuid), str(self.agent2.uuid)]

        validate_pre_approved_templates(agents_ids)

        mock_use_case_class.assert_called_once()
        self.assertEqual(mock_use_case.execute.call_count, 2)
        mock_use_case.execute.assert_any_call(self.agent1)
        mock_use_case.execute.assert_any_call(self.agent2)

    @patch("retail.agents.tasks.ValidatePreApprovedTemplatesUseCase")
    def test_validate_pre_approved_templates_with_nonexistent_agent_ids(
        self, mock_use_case_class
    ):
        mock_use_case = MagicMock()
        mock_use_case_class.return_value = mock_use_case

        nonexistent_uuid = str(uuid4())
        agents_ids = [str(self.agent1.uuid), nonexistent_uuid]

        validate_pre_approved_templates(agents_ids)

        mock_use_case_class.assert_called_once()
        mock_use_case.execute.assert_called_once_with(self.agent1)

    @patch("retail.agents.tasks.ValidatePreApprovedTemplatesUseCase")
    def test_validate_pre_approved_templates_with_empty_list(self, mock_use_case_class):
        mock_use_case = MagicMock()
        mock_use_case_class.return_value = mock_use_case

        agents_ids = []

        validate_pre_approved_templates(agents_ids)

        mock_use_case_class.assert_called_once()
        mock_use_case.execute.assert_not_called()
