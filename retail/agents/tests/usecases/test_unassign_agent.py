from uuid import uuid4

from django.test import TestCase

from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.unsassign import (
    UnassignAgentUseCase,
)
from retail.projects.models import Project


class UnassignAgentUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Project", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            is_oficial=True,
            lambda_arn="arn:aws:lambda:...",
            name="Agent",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent, project=self.project, channel_uuid=uuid4()
        )
        self.use_case = UnassignAgentUseCase()

    def test_execute_success(self):
        # Mock the audit function to avoid gRPC connection
        self.use_case.audit_func = lambda path, data: None

        self.assertTrue(
            IntegratedAgent.objects.filter(
                agent=self.agent, project=self.project
            ).exists()
        )
        self.use_case.execute(self.agent, str(self.project.uuid))
        self.assertFalse(
            IntegratedAgent.objects.filter(
                agent=self.agent, project=self.project, is_active=True
            ).exists()
        )

    def test_execute_not_found(self):
        self.integrated_agent.delete()
        with self.assertRaises(NotFound) as context:
            self.use_case.execute(self.agent, str(self.project.uuid))
        self.assertIn("Integrated agent not found", str(context.exception))

    def test_register_agent_unassign_event_format(self):
        """Test that _register_agent_unassign_event creates the correct event format."""
        # Mock the audit function to capture the data
        audit_calls = []

        def mock_audit_func(path, data):
            audit_calls.append(data)

        self.use_case.audit_func = mock_audit_func

        # Call the method directly
        self.use_case._register_agent_unassign_event(self.agent, str(self.project.uuid))

        # Verify that the event data was captured correctly
        self.assertEqual(len(audit_calls), 1)
        event_data = audit_calls[0]

        # Check that only relevant fields are present
        self.assertEqual(event_data["data"], {"event_type": "agent_unassigned"})
        self.assertEqual(event_data["project"], str(self.project.uuid))
        self.assertEqual(event_data["agent"], str(self.agent.uuid))

        # Check that fields not available for this event type are NOT present
        self.assertNotIn("status", event_data)
        self.assertNotIn("template", event_data)
        self.assertNotIn("template_variables", event_data)
        self.assertNotIn("contact_urn", event_data)
        self.assertNotIn("error", event_data)
        self.assertNotIn("request", event_data)
        self.assertNotIn("response", event_data)
