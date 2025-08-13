from django.test import TestCase

from unittest.mock import patch, MagicMock

from uuid import uuid4

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.usecases.update_integrated_agent import (
    UpdateIntegratedAgentUseCase,
)


class UpdateIntegratedAgentUseCaseTest(TestCase):
    def setUp(self):
        self.mock_global_rule_handler = MagicMock()
        self.mock_global_rule_handler.generate.return_value = (
            self.mock_global_rule_handler
        )
        self.mock_global_rule_handler.validate.return_value = (
            self.mock_global_rule_handler
        )
        self.mock_global_rule_handler.get_global_rule.return_value = "mocked_rule_code"
        self.usecase = UpdateIntegratedAgentUseCase(
            global_rule_handler=self.mock_global_rule_handler
        )
        self.mock_integrated_agent = MagicMock()
        self.mock_integrated_agent.uuid = uuid4()
        self.mock_integrated_agent.is_active = True
        self.mock_integrated_agent.contact_percentage = 10

    def test_execute_successfully_updates_contact_percentage(self):
        data = {"contact_percentage": 50}

        result = self.usecase.execute(self.mock_integrated_agent, data)

        self.assertEqual(result, self.mock_integrated_agent)
        self.assertEqual(self.mock_integrated_agent.contact_percentage, 50)
        self.mock_integrated_agent.save.assert_called_once()
        self.mock_global_rule_handler.generate.assert_not_called()

    @patch("retail.agents.usecases.update_integrated_agent.IntegratedAgent")
    def test_get_integrated_agent_raises_not_found_when_integrated_agent_does_not_exist(
        self, mock_integrated_agent_cls
    ):
        class DoesNotExist(Exception):
            pass

        mock_integrated_agent_cls.DoesNotExist = DoesNotExist
        mock_integrated_agent_cls.objects.get.side_effect = DoesNotExist()
        fake_uuid = uuid4()

        with self.assertRaises(NotFound) as context:
            self.usecase.get_integrated_agent(fake_uuid)
        self.assertIn(str(fake_uuid), str(context.exception))
        self.assertIn("Integrated agent not found", str(context.exception))

    @patch("retail.agents.usecases.update_integrated_agent.IntegratedAgent")
    def test_get_integrated_agent_returns_agent_when_found(
        self, mock_integrated_agent_cls
    ):
        mock_integrated_agent_cls.objects.get.return_value = self.mock_integrated_agent
        fake_uuid = uuid4()

        result = self.usecase.get_integrated_agent(fake_uuid)

        mock_integrated_agent_cls.objects.get.assert_called_once_with(
            uuid=fake_uuid, is_active=True
        )
        self.assertEqual(result, self.mock_integrated_agent)

    def test_execute_raises_validation_error_for_invalid_percentage(self):
        invalid_data = {"contact_percentage": 150}

        with self.assertRaises(ValidationError) as context:
            self.usecase.execute(self.mock_integrated_agent, invalid_data)
        self.assertIn("contact_percentage", context.exception.detail)
        self.assertIn(
            "Invalid percentage", str(context.exception.detail["contact_percentage"])
        )

    def test_execute_raises_validation_error_for_negative_percentage(self):
        invalid_data = {"contact_percentage": -10}

        with self.assertRaises(ValidationError) as context:
            self.usecase.execute(self.mock_integrated_agent, invalid_data)
        self.assertIn("contact_percentage", context.exception.detail)
        self.assertIn(
            "Invalid percentage", str(context.exception.detail["contact_percentage"])
        )

    def test_execute_updates_global_rule(self):
        data = {"global_rule": "some rule"}

        self.usecase.execute(self.mock_integrated_agent, data)

        self.mock_global_rule_handler.generate.assert_called_once_with(
            self.mock_integrated_agent, "some rule"
        )
        self.mock_global_rule_handler.validate.assert_called_once()
        self.mock_global_rule_handler.get_global_rule.assert_called_once()
        self.assertEqual(self.mock_integrated_agent.global_rule_prompt, "some rule")
        self.mock_integrated_agent.save.assert_called_once()

    def test_execute_sets_global_rule_to_none_when_global_rule_is_none(self):
        data = {"global_rule": None}

        result = self.usecase.execute(self.mock_integrated_agent, data)

        self.mock_global_rule_handler.generate.assert_not_called()
        self.mock_global_rule_handler.validate.assert_not_called()
        self.mock_global_rule_handler.get_global_rule.assert_not_called()

        self.assertIsNone(self.mock_integrated_agent.global_rule_code)
        self.assertIsNone(self.mock_integrated_agent.global_rule_prompt)

        self.mock_integrated_agent.save.assert_called_once()
        self.assertEqual(result, self.mock_integrated_agent)

    def test_execute_sets_global_rule_to_none_when_global_rule_is_empty_string(self):
        data = {"global_rule": ""}

        result = self.usecase.execute(self.mock_integrated_agent, data)

        self.mock_global_rule_handler.generate.assert_not_called()
        self.mock_global_rule_handler.validate.assert_not_called()
        self.mock_global_rule_handler.get_global_rule.assert_not_called()

        self.assertIsNone(self.mock_integrated_agent.global_rule_code)
        self.assertIsNone(self.mock_integrated_agent.global_rule_prompt)

        self.mock_integrated_agent.save.assert_called_once()
        self.assertEqual(result, self.mock_integrated_agent)

    def test_execute_updates_both_contact_percentage_and_global_rule(self):
        data = {"contact_percentage": 75, "global_rule": "new rule"}

        result = self.usecase.execute(self.mock_integrated_agent, data)

        self.assertEqual(self.mock_integrated_agent.contact_percentage, 75)

        self.mock_global_rule_handler.generate.assert_called_once_with(
            self.mock_integrated_agent, "new rule"
        )
        self.mock_global_rule_handler.validate.assert_called_once()
        self.mock_global_rule_handler.get_global_rule.assert_called_once()
        self.assertEqual(self.mock_integrated_agent.global_rule_prompt, "new rule")
        self.assertEqual(
            self.mock_integrated_agent.global_rule_code, "mocked_rule_code"
        )

        self.mock_integrated_agent.save.assert_called_once()
        self.assertEqual(result, self.mock_integrated_agent)

    def test_execute_updates_contact_percentage_and_clears_global_rule(self):
        data = {"contact_percentage": 25, "global_rule": None}

        result = self.usecase.execute(self.mock_integrated_agent, data)

        self.assertEqual(self.mock_integrated_agent.contact_percentage, 25)

        self.mock_global_rule_handler.generate.assert_not_called()
        self.assertIsNone(self.mock_integrated_agent.global_rule_code)
        self.assertIsNone(self.mock_integrated_agent.global_rule_prompt)

        self.mock_integrated_agent.save.assert_called_once()
        self.assertEqual(result, self.mock_integrated_agent)
