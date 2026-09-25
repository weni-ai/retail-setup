from uuid import uuid4
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.unassign import (
    UnassignAgentUseCase,
)
from retail.clients.exceptions import CustomAPIException
from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService


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
        self.use_case = UnassignAgentUseCase(vtex_io_service=MagicMock())

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

    @override_settings(BACK_IN_STOCK_AGENT_UUID="")
    def test_execute_does_not_uninstall_other_agents(self):
        self.use_case.audit_func = lambda path, data: None
        self.project.vtex_account = "recorrenciacharlie"
        self.project.save(update_fields=["vtex_account"])

        self.use_case.execute(self.agent, str(self.project.uuid))

        self.use_case.vtex_io_service.uninstall_back_in_stock_app.assert_not_called()

    def test_execute_uninstalls_back_in_stock_app(self):
        self.use_case.audit_func = lambda path, data: None
        self.project.vtex_account = "recorrenciacharlie"
        self.project.save(update_fields=["vtex_account"])

        with override_settings(BACK_IN_STOCK_AGENT_UUID=str(self.agent.uuid)):
            self.use_case.execute(self.agent, str(self.project.uuid))

        self.use_case.vtex_io_service.uninstall_back_in_stock_app.assert_called_once_with(
            "recorrenciacharlie"
        )
        self.assertFalse(
            self.integrated_agent.__class__.objects.get(
                pk=self.integrated_agent.pk
            ).is_active
        )

    def test_execute_stays_unassigned_when_uninstall_fails(self):
        self.use_case.audit_func = lambda path, data: None
        self.project.vtex_account = "recorrenciacharlie"
        self.project.save(update_fields=["vtex_account"])
        self.use_case.vtex_io_service.uninstall_back_in_stock_app.return_value = None

        with override_settings(BACK_IN_STOCK_AGENT_UUID=str(self.agent.uuid)):
            self.use_case.execute(self.agent, str(self.project.uuid))

        self.assertFalse(
            IntegratedAgent.objects.filter(
                pk=self.integrated_agent.pk, is_active=True
            ).exists()
        )

    @patch("retail.services.vtex_io.service.time.sleep")
    def test_execute_retries_uninstall_and_deactivates_agent(self, _sleep):
        self.use_case.audit_func = lambda path, data: None
        self.project.vtex_account = "recorrenciacharlie"
        self.project.save(update_fields=["vtex_account"])
        client = MagicMock()
        client.uninstall_back_in_stock_app.side_effect = [
            CustomAPIException(detail="unavailable", status_code=503),
            {"uninstalled": True},
        ]
        self.use_case.vtex_io_service = VtexIOService(client=client)

        with override_settings(BACK_IN_STOCK_AGENT_UUID=str(self.agent.uuid)):
            self.use_case.execute(self.agent, str(self.project.uuid))

        self.assertEqual(client.uninstall_back_in_stock_app.call_count, 2)
        client.uninstall_back_in_stock_app.assert_called_with("recorrenciacharlie")
        self.assertFalse(
            IntegratedAgent.objects.filter(
                pk=self.integrated_agent.pk, is_active=True
            ).exists()
        )
        _sleep.assert_called_once()

    def test_execute_does_not_retry_uninstall_on_client_error(self):
        self.use_case.audit_func = lambda path, data: None
        self.project.vtex_account = "recorrenciacharlie"
        self.project.save(update_fields=["vtex_account"])
        client = MagicMock()
        client.uninstall_back_in_stock_app.side_effect = CustomAPIException(
            detail="unauthorized", status_code=401
        )
        self.use_case.vtex_io_service = VtexIOService(client=client)

        with override_settings(BACK_IN_STOCK_AGENT_UUID=str(self.agent.uuid)):
            self.use_case.execute(self.agent, str(self.project.uuid))

        client.uninstall_back_in_stock_app.assert_called_once_with("recorrenciacharlie")
        self.assertFalse(
            IntegratedAgent.objects.filter(
                pk=self.integrated_agent.pk, is_active=True
            ).exists()
        )
