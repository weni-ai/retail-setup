from unittest.mock import MagicMock
from django.test import TestCase

from retail.clients.exceptions import CustomAPIException
from retail.services.nexus.service import NexusService


class TestNexusService(TestCase):
    def setUp(self):
        self.mock_nexus_client = MagicMock()
        self.service = NexusService(nexus_client=self.mock_nexus_client)
        self.project_uuid = "project-uuid-123"
        self.agent_uuid = "agent-uuid-123"

    def test_init_with_nexus_client(self):
        service = NexusService(nexus_client=self.mock_nexus_client)
        self.assertEqual(service.nexus_client, self.mock_nexus_client)

    def test_list_agents_success(self):
        expected_response = {"agents": [{"id": "agent1", "name": "Agent 1"}]}
        self.mock_nexus_client.list_agents.return_value = expected_response

        result = self.service.list_agents(self.project_uuid)

        self.mock_nexus_client.list_agents.assert_called_once_with(self.project_uuid)
        self.assertEqual(result, expected_response)

    def test_list_agents_custom_api_exception(self):
        exception = CustomAPIException(status_code=404, detail="Not found")
        self.mock_nexus_client.list_agents.side_effect = exception

        result = self.service.list_agents(self.project_uuid)

        self.mock_nexus_client.list_agents.assert_called_once_with(self.project_uuid)
        self.assertIsNone(result)

    def test_integrate_agent_success(self):
        expected_response = {"integration_id": "123", "status": "integrated"}
        self.mock_nexus_client.integrate_agent.return_value = expected_response

        result = self.service.integrate_agent(self.project_uuid, self.agent_uuid)

        self.mock_nexus_client.integrate_agent.assert_called_once_with(
            self.project_uuid, self.agent_uuid
        )
        self.assertEqual(result, expected_response)

    def test_integrate_agent_custom_api_exception(self):
        exception = CustomAPIException(status_code=400, detail="Bad request")
        self.mock_nexus_client.integrate_agent.side_effect = exception

        result = self.service.integrate_agent(self.project_uuid, self.agent_uuid)

        self.mock_nexus_client.integrate_agent.assert_called_once_with(
            self.project_uuid, self.agent_uuid
        )
        self.assertIsNone(result)

    def test_remove_agent_success(self):
        expected_response = {"status": "removed"}
        self.mock_nexus_client.remove_agent.return_value = expected_response

        result = self.service.remove_agent(self.project_uuid, self.agent_uuid)

        self.mock_nexus_client.remove_agent.assert_called_once_with(
            self.project_uuid, self.agent_uuid
        )
        self.assertEqual(result, expected_response)

    def test_remove_agent_custom_api_exception(self):
        exception = CustomAPIException(status_code=500, detail="Internal error")
        self.mock_nexus_client.remove_agent.side_effect = exception

        result = self.service.remove_agent(self.project_uuid, self.agent_uuid)

        self.mock_nexus_client.remove_agent.assert_called_once_with(
            self.project_uuid, self.agent_uuid
        )
        self.assertIsNone(result)

    def test_list_integrated_agents_success(self):
        expected_response = {
            "integrated_agents": [
                {"id": "agent1", "name": "Agent 1", "status": "active"}
            ]
        }
        self.mock_nexus_client.list_integrated_agents.return_value = expected_response

        result = self.service.list_integrated_agents(self.project_uuid)

        self.mock_nexus_client.list_integrated_agents.assert_called_once_with(
            self.project_uuid
        )
        self.assertEqual(result, expected_response)

    def test_list_integrated_agents_custom_api_exception(self):
        exception = CustomAPIException(status_code=403, detail="Forbidden")
        self.mock_nexus_client.list_integrated_agents.side_effect = exception

        result = self.service.list_integrated_agents(self.project_uuid)

        self.mock_nexus_client.list_integrated_agents.assert_called_once_with(
            self.project_uuid
        )
        self.assertIsNone(result)
