from unittest.mock import Mock

from django.test import TestCase

from uuid import uuid4

from retail.projects.models import Project
from retail.agents.domains.agent_management.models import Agent, AgentRule
from retail.agents.domains.agent_management.usecases.validate_templates import (
    ValidateAgentRulesUseCase,
)


class ValidateAgentRulesUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(uuid=uuid4(), name="Test Project")
        self.agent = Agent.objects.create(
            name="Test Agent", project=self.project, language="pt_BR"
        )

        self.library_rule = AgentRule.objects.create(
            name="valid_template",
            content="old content",
            source_type="LIBRARY",
            agent=self.agent,
            slug="valid-rule",
            display_name="Valid Template",
            start_condition="test",
        )
        self.user_existing_rule = AgentRule.objects.create(
            name="user_template",
            content="should not change",
            source_type="USER_EXISTING",
            agent=self.agent,
            slug="user-rule",
            display_name="User Template",
            start_condition="test",
        )

        self.meta_service_mock = Mock()
        self.meta_service_mock.get_pre_approved_template.side_effect = (
            lambda name, language: (
                {
                    "data": [
                        {
                            "name": "valid_template",
                            "body": "new content",
                            "header": {"type": "TEXT", "text": "Header"},
                            "body_params": ["param1", "param2"],
                            "footer": "Footer text",
                            "buttons": [{"type": "QUICK_REPLY", "text": "Button"}],
                            "category": "MARKETING",
                            "language": "pt_BR",
                        }
                    ]
                }
                if name == "valid_template"
                else {"data": []}
            )
        )

        self.template_adapter_mock = Mock()
        self.template_adapter_mock.header_transformer.transform.return_value = {
            "type": "TEXT",
            "text": "Header",
        }

        self.usecase = ValidateAgentRulesUseCase(
            meta_service=self.meta_service_mock,
            template_adapter=self.template_adapter_mock,
        )

    def test_get_template_info_returns_info_when_exists(self):
        info = self.usecase._get_template_info("valid_template", "pt_BR")

        self.meta_service_mock.get_pre_approved_template.assert_called_with(
            "valid_template", "pt_BR"
        )
        self.template_adapter_mock.header_transformer.transform.assert_called_with(
            {
                "name": "valid_template",
                "body": "new content",
                "header": {"type": "TEXT", "text": "Header"},
                "body_params": ["param1", "param2"],
                "footer": "Footer text",
                "buttons": [{"type": "QUICK_REPLY", "text": "Button"}],
                "category": "MARKETING",
                "language": "pt_BR",
            }
        )

        expected_info = {
            "name": "valid_template",
            "content": "new content",
            "metadata": {
                "header": {"type": "TEXT", "text": "Header"},
                "body": "new content",
                "body_params": ["param1", "param2"],
                "footer": "Footer text",
                "buttons": [{"type": "QUICK_REPLY", "text": "Button"}],
                "category": "MARKETING",
                "language": "pt_BR",
            },
        }

        self.assertEqual(info, expected_info)

    def test_get_template_info_returns_none_when_not_exists(self):
        info = self.usecase._get_template_info("nonexistent_template", "pt_BR")

        self.meta_service_mock.get_pre_approved_template.assert_called_with(
            "nonexistent_template", "pt_BR"
        )
        self.assertIsNone(info)

    def test_execute_only_validates_library_rules(self):
        """Only LIBRARY rules should be validated against Meta API."""
        self.usecase.execute(self.agent)

        self.library_rule.refresh_from_db()
        self.user_existing_rule.refresh_from_db()

        # LIBRARY rule should have updated metadata and content
        self.assertEqual(self.library_rule.name, "valid_template")
        self.assertEqual(self.library_rule.content, "new content")

        expected_metadata = {
            "header": {"type": "TEXT", "text": "Header"},
            "body": "new content",
            "body_params": ["param1", "param2"],
            "footer": "Footer text",
            "buttons": [{"type": "QUICK_REPLY", "text": "Button"}],
            "category": "MARKETING",
            "language": "pt_BR",
        }
        self.assertEqual(self.library_rule.metadata, expected_metadata)

        # USER_EXISTING rule should NOT be touched
        self.assertEqual(self.user_existing_rule.content, "should not change")
        self.assertEqual(self.user_existing_rule.source_type, "USER_EXISTING")

    def test_execute_with_no_library_rules(self):
        """No Meta API calls when agent has no LIBRARY rules."""
        self.library_rule.delete()
        self.usecase.execute(self.agent)

        self.meta_service_mock.get_pre_approved_template.assert_not_called()
        self.template_adapter_mock.header_transformer.transform.assert_not_called()

    def test_execute_library_rule_not_found_in_meta(self):
        """LIBRARY rule not found in Meta should log warning, not crash."""
        self.library_rule.name = "nonexistent_template"
        self.library_rule.save()

        self.usecase.execute(self.agent)

        self.library_rule.refresh_from_db()
        # Rule should still exist with LIBRARY source_type
        self.assertEqual(self.library_rule.source_type, "LIBRARY")

    def test_template_adapter_is_called_correctly(self):
        self.usecase._get_template_info("valid_template", "pt_BR")
        self.template_adapter_mock.header_transformer.transform.assert_called_once_with(
            {
                "name": "valid_template",
                "body": "new content",
                "header": {"type": "TEXT", "text": "Header"},
                "body_params": ["param1", "param2"],
                "footer": "Footer text",
                "buttons": [{"type": "QUICK_REPLY", "text": "Button"}],
                "category": "MARKETING",
                "language": "pt_BR",
            }
        )
