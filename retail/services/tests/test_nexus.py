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

    def test_check_agent_builder_exists_success(self):
        expected = {"data": {"has_agent": True, "name": "Test Manager"}}
        self.mock_nexus_client.check_agent_builder_exists.return_value = expected

        result = self.service.check_agent_builder_exists(self.project_uuid)

        self.mock_nexus_client.check_agent_builder_exists.assert_called_once_with(
            self.project_uuid
        )
        self.assertEqual(result, expected)

    def test_check_agent_builder_exists_api_exception(self):
        exception = CustomAPIException(status_code=404, detail="Not found")
        self.mock_nexus_client.check_agent_builder_exists.side_effect = exception

        result = self.service.check_agent_builder_exists(self.project_uuid)

        self.assertIsNone(result)

    def test_configure_agent_attributes_success(self):
        payload = {"agent": {"name": "Test Manager"}, "links": []}
        expected = {"status": "ok"}
        self.mock_nexus_client.configure_agent_attributes.return_value = expected

        result = self.service.configure_agent_attributes(self.project_uuid, payload)

        self.mock_nexus_client.configure_agent_attributes.assert_called_once_with(
            self.project_uuid, payload
        )
        self.assertEqual(result, expected)

    def test_configure_agent_attributes_api_exception(self):
        payload = {"agent": {"name": "Test Manager"}, "links": []}
        exception = CustomAPIException(status_code=500, detail="Error")
        self.mock_nexus_client.configure_agent_attributes.side_effect = exception

        result = self.service.configure_agent_attributes(self.project_uuid, payload)

        self.assertIsNone(result)

    def test_create_agent_credentials_success(self):
        credentials = [
            {
                "name": "wpp_flow_uuid",
                "label": "WhatsApp Flow UUID",
                "is_confidential": True,
                "value": "flow-meta-123",
            }
        ]
        expected = {
            "message": "Credentials created successfully",
            "created_credentials": ["wpp_flow_uuid"],
        }
        self.mock_nexus_client.create_agent_credentials.return_value = expected

        result = self.service.create_agent_credentials(
            project_uuid=self.project_uuid,
            agent_uuid=self.agent_uuid,
            credentials=credentials,
        )

        self.mock_nexus_client.create_agent_credentials.assert_called_once_with(
            project_uuid=self.project_uuid,
            agent_uuid=self.agent_uuid,
            credentials=credentials,
        )
        self.assertEqual(result, expected)

    def test_create_agent_credentials_returns_none_on_api_exception(self):
        self.mock_nexus_client.create_agent_credentials.side_effect = (
            CustomAPIException(status_code=502, detail="bad gateway")
        )

        result = self.service.create_agent_credentials(
            project_uuid=self.project_uuid,
            agent_uuid=self.agent_uuid,
            credentials=[],
        )

        self.assertIsNone(result)

    def test_upload_content_base_files_batch_success(self):
        files = [("page.txt", b"content", "text/plain")]
        expected = {
            "files": [
                {
                    "uuid": "file-uuid-1",
                    "extension_file": "txt",
                    "filename": "page.txt",
                }
            ]
        }
        self.mock_nexus_client.upload_content_base_files_batch.return_value = expected

        result = self.service.upload_content_base_files_batch(self.project_uuid, files)

        self.mock_nexus_client.upload_content_base_files_batch.assert_called_once_with(
            self.project_uuid, files, "txt"
        )
        self.assertEqual(result, expected)

    def test_upload_content_base_files_batch_api_exception(self):
        files = [("page.txt", b"content", "text/plain")]
        self.mock_nexus_client.upload_content_base_files_batch.side_effect = (
            CustomAPIException(status_code=400, detail="Bad request")
        )

        result = self.service.upload_content_base_files_batch(self.project_uuid, files)

        self.assertIsNone(result)

    def test_get_content_base_batch_progress_success(self):
        file_uuids = ["uuid-1", "uuid-2"]
        expected = {
            "total": 2,
            "completed": 1,
            "failed": 0,
            "remaining": 1,
            "progress_percentage": 50,
            "is_complete": False,
            "status": "processing",
        }
        self.mock_nexus_client.get_content_base_batch_progress.return_value = expected

        result = self.service.get_content_base_batch_progress(
            self.project_uuid, file_uuids
        )

        self.mock_nexus_client.get_content_base_batch_progress.assert_called_once_with(
            self.project_uuid, file_uuids
        )
        self.assertEqual(result, expected)

    def test_get_content_base_batch_progress_api_exception(self):
        file_uuids = ["uuid-1"]
        self.mock_nexus_client.get_content_base_batch_progress.side_effect = (
            CustomAPIException(status_code=500, detail="Error")
        )

        result = self.service.get_content_base_batch_progress(
            self.project_uuid, file_uuids
        )

        self.assertIsNone(result)
