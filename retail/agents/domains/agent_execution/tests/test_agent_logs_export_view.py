"""End-to-end tests for ``POST /assigneds/{agent_uuid}/logs/export/``.

The endpoint is fire-and-forget: the view validates the body, enqueues
the Celery task, and returns ``202 { "requested": true }``. These tests
pin that loop end-to-end.
"""

from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.internal.test_mixins import (
    BaseTestMixin,
    ConnectServicePermissionScenarios,
    with_test_settings,
)
from retail.projects.models import Project


User = get_user_model()


@with_test_settings
class AgentLogsExportViewTest(BaseTestMixin, APITestCase):
    def setUp(self):
        super().setUp()

        self.project = Project.objects.create(name="P1", uuid=uuid4())
        self.other_project = Project.objects.create(name="P2", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="A",
            slug="a",
            description="",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=self.agent, project=self.project
        )

        self.user = User.objects.create_user(
            username="tester", password="x", email="tester@example.com"
        )
        self.client.force_authenticate(self.user)

        self.url = reverse(
            "agent-logs-export",
            kwargs={"agent_uuid": str(self.integrated_agent.uuid)},
        )

    def _post(self, body=None, project_uuid=None, auth_token: str = "Bearer x"):
        headers = {}
        if project_uuid is not None:
            headers["HTTP_PROJECT_UUID"] = str(project_uuid)
        if auth_token:
            headers["HTTP_AUTHORIZATION"] = auth_token
        return self.client.post(self.url, data=body or {}, format="json", **headers)

    def test_missing_project_uuid_is_forbidden(self):
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("retail.agents.domains.agent_execution.views.task_export_agent_logs")
    def test_returns_202_and_requested_true_on_empty_body(self, mock_task):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )

        response = self._post(project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.json(), {"requested": True})
        self.assertTrue(mock_task.apply_async.called)

    @patch("retail.agents.domains.agent_execution.views.task_export_agent_logs")
    def test_forwards_filters_to_celery_task(self, mock_task):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        template_uuid = uuid4()
        body = {
            "search": "ORD-",
            "date": "2026-05-01",
            "template_uuids": [str(template_uuid)],
            "statuses": ["sent", "skipped"],
        }

        response = self._post(body=body, project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        kwargs = mock_task.apply_async.call_args.kwargs["kwargs"]
        self.assertEqual(kwargs["agent_uuid"], str(self.integrated_agent.uuid))
        self.assertEqual(kwargs["project_uuid"], str(self.project.uuid))
        self.assertEqual(kwargs["search"], "ORD-")
        self.assertEqual(kwargs["date"], "2026-05-01")
        self.assertEqual(kwargs["template_uuids"], [str(template_uuid)])
        self.assertEqual(kwargs["statuses"], ["sent", "skipped"])

    def test_invalid_status_is_rejected_with_400(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )

        response = self._post(
            body={"statuses": ["bogus"]}, project_uuid=self.project.uuid
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_agent_returns_404(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        url = reverse("agent-logs-export", kwargs={"agent_uuid": str(uuid4())})

        response = self.client.post(
            url,
            data={},
            format="json",
            HTTP_PROJECT_UUID=str(self.project.uuid),
            HTTP_AUTHORIZATION="Bearer x",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("retail.agents.domains.agent_execution.views.task_export_agent_logs")
    def test_other_project_cannot_request_export(self, mock_task):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )

        response = self._post(project_uuid=self.other_project.uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_task.apply_async.assert_not_called()
