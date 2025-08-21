from django.test import TestCase

from uuid import uuid4

from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_management.models import Agent, PreApprovedTemplate
from retail.agents.domains.agent_management.usecases.retrieve import (
    RetrieveAgentUseCase,
)
from retail.projects.models import Project


class RetrieveAgentUseCaseTest(TestCase):
    def setUp(self):
        """Set up test data for all test methods."""
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            organization_uuid=uuid4(),
            vtex_account="test-store",
        )

        self.agent = Agent.objects.create(
            name="Test Agent",
            slug="test-agent",
            description="A test agent for testing purposes",
            is_oficial=False,
            lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:test-agent",
            project=self.project,
            credentials={"api_key": {"label": "API Key", "is_confidential": True}},
            language="pt_BR",
            examples=[{"input": "test", "output": "response"}],
        )

        self.template1 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            slug="template-1",
            name="Template 1",
            display_name="Test Template 1",
            content="Hello {{1}}!",
            is_valid=True,
            start_condition="greeting",
            metadata={"category": "greeting"},
        )

        self.template2 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            slug="template-2",
            name="Template 2",
            display_name="Test Template 2",
            content="Goodbye {{1}}!",
            is_valid=True,
            start_condition="farewell",
            metadata={"category": "farewell"},
        )

    def test_execute_returns_agent_when_exists(self):
        """Test that execute returns the agent when it exists."""
        result = RetrieveAgentUseCase.execute(self.agent.uuid)

        self.assertEqual(result.uuid, self.agent.uuid)
        self.assertEqual(result.name, "Test Agent")
        self.assertEqual(result.slug, "test-agent")
        self.assertEqual(result.description, "A test agent for testing purposes")
        self.assertEqual(result.is_oficial, False)
        self.assertEqual(result.project, self.project)
        self.assertEqual(result.language, "pt_BR")

        self.assertIn("api_key", result.credentials)
        self.assertEqual(result.credentials["api_key"]["label"], "API Key")

        self.assertEqual(len(result.examples), 1)
        self.assertEqual(result.examples[0]["input"], "test")

        templates = list(result.templates.all())
        self.assertEqual(len(templates), 2)

        template_names = [t.name for t in templates]
        self.assertIn("Template 1", template_names)
        self.assertIn("Template 2", template_names)

        template1 = next(t for t in templates if t.name == "Template 1")
        self.assertEqual(template1.slug, "template-1")
        self.assertEqual(template1.display_name, "Test Template 1")
        self.assertEqual(template1.content, "Hello {{1}}!")
        self.assertTrue(template1.is_valid)
        self.assertEqual(template1.start_condition, "greeting")
        self.assertEqual(template1.metadata["category"], "greeting")

    def test_execute_returns_official_agent(self):
        """Test that execute works correctly for official agents."""
        official_agent = Agent.objects.create(
            name="Official Agent",
            slug="official-agent",
            description="An official agent",
            is_oficial=True,
            project=self.project,
            lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:official-agent",
            credentials={},
            language="pt_BR",
            examples=[],
        )

        result = RetrieveAgentUseCase.execute(official_agent.uuid)

        self.assertEqual(result.uuid, official_agent.uuid)
        self.assertEqual(result.name, "Official Agent")
        self.assertTrue(result.is_oficial)
        self.assertEqual(result.project, self.project)

    def test_execute_raises_not_found_when_agent_does_not_exist(self):
        """Test that execute raises NotFound when agent doesn't exist."""
        fake_uuid = uuid4()

        with self.assertRaises(NotFound) as context:
            RetrieveAgentUseCase.execute(fake_uuid)

        self.assertIn(str(fake_uuid), str(context.exception))
        self.assertIn("Agent not found", str(context.exception))
