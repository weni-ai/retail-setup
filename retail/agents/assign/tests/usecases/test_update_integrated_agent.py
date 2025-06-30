from django.test import TestCase

from unittest.mock import patch, MagicMock

from uuid import uuid4

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.assign.usecases.update_integrated_agent import (
    UpdateIntegratedAgentUseCase,
)


class UpdateIntegratedAgentUseCaseTest(TestCase):
    def setUp(self):
        self.usecase = UpdateIntegratedAgentUseCase()
        self.mock_integrated_agent = MagicMock()
        self.mock_integrated_agent.uuid = uuid4()
        self.mock_integrated_agent.is_active = True
        self.mock_integrated_agent.contact_percentage = 10

    @patch("retail.agents.assign.usecases.update_integrated_agent.IntegratedAgent")
    def test_execute_successfully_updates_contact_percentage(
        self, mock_integrated_agent_cls
    ):
        mock_integrated_agent_cls.objects.get.return_value = self.mock_integrated_agent
        data = {"contact_percentage": 50}

        result = self.usecase.execute(self.mock_integrated_agent.uuid, data)

        mock_integrated_agent_cls.objects.get.assert_called_once_with(
            uuid=self.mock_integrated_agent.uuid, is_active=True
        )
        self.assertEqual(result, self.mock_integrated_agent)
        self.assertEqual(self.mock_integrated_agent.contact_percentage, 50)
        self.mock_integrated_agent.save.assert_called_once()

    @patch("retail.agents.assign.usecases.update_integrated_agent.IntegratedAgent")
    def test_execute_raises_not_found_when_integrated_agent_does_not_exist(
        self, mock_integrated_agent_cls
    ):
        class DoesNotExist(Exception):
            pass

        mock_integrated_agent_cls.DoesNotExist = DoesNotExist
        mock_integrated_agent_cls.objects.get.side_effect = DoesNotExist()
        fake_uuid = uuid4()
        data = {"contact_percentage": 30}

        with self.assertRaises(NotFound) as context:
            self.usecase.execute(fake_uuid, data)
        self.assertIn(str(fake_uuid), str(context.exception))
        self.assertIn("Integrated agent not found", str(context.exception))

    @patch("retail.agents.assign.usecases.update_integrated_agent.IntegratedAgent")
    def test_execute_raises_validation_error_for_invalid_percentage(
        self, mock_integrated_agent_cls
    ):
        mock_integrated_agent_cls.objects.get.return_value = self.mock_integrated_agent
        invalid_data = {"contact_percentage": 150}

        with self.assertRaises(ValidationError) as context:
            self.usecase.execute(self.mock_integrated_agent.uuid, invalid_data)
        self.assertIn("contact_percentage", context.exception.detail)
        self.assertIn(
            "Invalid percentage", str(context.exception.detail["contact_percentage"])
        )

    @patch("retail.agents.assign.usecases.update_integrated_agent.IntegratedAgent")
    def test_execute_raises_validation_error_for_negative_percentage(
        self, mock_integrated_agent_cls
    ):
        mock_integrated_agent_cls.objects.get.return_value = self.mock_integrated_agent
        invalid_data = {"contact_percentage": -10}

        with self.assertRaises(ValidationError) as context:
            self.usecase.execute(self.mock_integrated_agent.uuid, invalid_data)
        self.assertIn("contact_percentage", context.exception.detail)
        self.assertIn(
            "Invalid percentage", str(context.exception.detail["contact_percentage"])
        )
