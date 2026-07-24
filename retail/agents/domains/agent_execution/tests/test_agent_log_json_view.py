"""End-to-end tests for ``GET /assigneds/{agent_uuid}/logs/{log_uuid}/json/``.

The proxy view reads the stored trace payload from S3 server-side. These
tests exercise the view: permission checks, tenant scoping, and the
404/200 mapping. The S3 read itself is stubbed by patching the storage
service the use case builds.
"""

from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.internal.test_mixins import (
    BaseTestMixin,
    ConnectServicePermissionScenarios,
    with_test_settings,
)
from retail.projects.models import Project


User = get_user_model()

_STORAGE_PATH = (
    "retail.agents.domains.agent_execution.usecases."
    "get_agent_log_json.ExecutionTracesStorageService"
)


@with_test_settings
class AgentLogJsonViewTest(BaseTestMixin, APITestCase):
    def setUp(self):
        super().setUp()

        self.project = Project.objects.create(name="P1", uuid=uuid4())
        self.other_project = Project.objects.create(name="P2", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent",
            slug="agent",
            description="",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=self.agent, project=self.project
        )

        self.user = User.objects.create_user(
            username="tester", password="x", email="tester@example.com"
        )
        self.start_retail_auth(
            project_uuid=self.project.uuid, user_email=self.user.email
        )

        self.execution = AgentExecution.objects.create(
            uuid=uuid4(),
            contact_urn="whatsapp:+5511999998888",
            status=AgentExecutionStatus.ERROR,
            integrated_agent=self.integrated_agent,
            traces_s3_key="executions/sample/traces.json",
        )

    def _url(self, log_uuid=None) -> str:
        return reverse(
            "agent-log-json",
            kwargs={
                "agent_uuid": str(self.integrated_agent.uuid),
                "log_uuid": str(log_uuid or self.execution.uuid),
            },
        )

    def _request(self, url=None, project_uuid=None, auth_token="Bearer x"):
        self.set_retail_auth(
            authenticated=auth_token is not None,
            project_uuid=project_uuid,
            user_email=self.user.email,
        )
        return self.client.get(url or self._url())

    def test_missing_project_header_is_forbidden(self):
        response = self._request()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_project_cannot_read_this_agents_log(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )

        response = self._request(project_uuid=self.other_project.uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(_STORAGE_PATH)
    def test_returns_payload_on_happy_path(self, mock_storage_cls):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        mock_storage_cls.return_value.read_traces_payload.return_value = (
            b'[{"type": "webhook_received", "data": {"a": 1}}]'
        )

        response = self._request(project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(), [{"type": "webhook_received", "data": {"a": 1}}]
        )

    @patch(_STORAGE_PATH)
    def test_missing_payload_returns_404(self, mock_storage_cls):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        mock_storage_cls.return_value.read_traces_payload.return_value = None

        response = self._request(project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unknown_log_returns_404(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )

        response = self._request(
            url=self._url(log_uuid=uuid4()), project_uuid=self.project.uuid
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unknown_agent_returns_404(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        url = reverse(
            "agent-log-json",
            kwargs={
                "agent_uuid": str(uuid4()),
                "log_uuid": str(self.execution.uuid),
            },
        )

        response = self._request(url=url, project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
