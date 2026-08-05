"""End-to-end tests for ``GET /assigneds/{agent_uuid}/logs/``.

These tests exercise the view: query parsing, permission checks,
response shape, status mapping, the ``has_json`` rules, and filter
forwarding to the use case.
"""

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
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
from retail.agents.domains.agent_management.models import (
    Agent,
    PreApprovedTemplate,
)
from retail.broadcasts.models import BroadcastMessage, BroadcastStatus
from retail.internal.test_mixins import (
    BaseTestMixin,
    ConnectServicePermissionScenarios,
    with_test_settings,
)
from retail.projects.models import Project
from retail.templates.models import Template


User = get_user_model()


@with_test_settings
class AgentLogsViewTest(BaseTestMixin, APITestCase):
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
        self.other_integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=self.agent, project=self.other_project
        )

        self.user = User.objects.create_user(
            username="tester", password="x", email="tester@example.com"
        )
        self.start_retail_auth(
            project_uuid=self.project.uuid, user_email=self.user.email
        )

        self.url = reverse(
            "agent-logs", kwargs={"agent_uuid": str(self.integrated_agent.uuid)}
        )

    def _request(
        self, project_uuid=None, query_string: str = "", auth_token: str = "Bearer x"
    ):
        self.set_retail_auth(
            authenticated=auth_token is not None,
            project_uuid=project_uuid,
            user_email=self.user.email,
        )
        url = self.url + (f"?{query_string}" if query_string else "")
        return self.client.get(url)

    def _make_execution(self, **overrides) -> AgentExecution:
        defaults = dict(
            uuid=uuid4(),
            contact_urn="whatsapp:+5511999998888",
            status=AgentExecutionStatus.SUCCESS,
            integrated_agent=self.integrated_agent,
            order_id="ORD-1",
            amount=Decimal("100.00"),
            currency="BRL",
            traces_s3_key="executions/sample/traces.json",
        )
        defaults.update(overrides)
        return AgentExecution.objects.create(**defaults)

    def test_missing_project_header_is_forbidden(self):
        response = self._request()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_project_cannot_read_this_agents_logs(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        self._make_execution()

        response = self._request(project_uuid=self.other_project.uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_returns_paginated_results_in_log_shape(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )

        execution = self._make_execution()
        AgentExecution.objects.filter(uuid=execution.uuid).update(
            created_on=datetime(2026, 5, 1, 14, 2, 0, tzinfo=dt_timezone.utc)
        )

        response = self._request(project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn("results", body)
        self.assertIn("pagination", body)
        self.assertEqual(body["pagination"], {"page": 1, "page_size": 20, "total": 1})

        row = body["results"][0]
        self.assertEqual(row["uuid"], str(execution.uuid))
        self.assertEqual(row["status"], "sent")
        self.assertEqual(row["contact"], "+55 11 99999-8888")
        self.assertEqual(row["order_id"], "ORD-1")
        self.assertEqual(row["amount"], {"value": "100.00", "currency": "BRL"})
        self.assertIn("Message handed off to the messaging provider", row["summary"])
        # A terminal ``sent`` row has a stored payload, so ``has_json``
        # is True; the client fetches it through the proxy endpoint.
        self.assertTrue(row["has_json"])

    def test_has_json_is_true_for_terminal_rows_and_false_for_processing(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )

        skipped = self._make_execution(status=AgentExecutionStatus.SKIP)
        errored = self._make_execution(status=AgentExecutionStatus.ERROR)
        sent = self._make_execution(status=AgentExecutionStatus.SUCCESS)
        processing = self._make_execution(status=AgentExecutionStatus.PROCESSING)

        response = self._request(project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = {r["uuid"]: r for r in response.json()["results"]}

        self.assertTrue(rows[str(skipped.uuid)]["has_json"])
        self.assertTrue(rows[str(errored.uuid)]["has_json"])
        self.assertTrue(rows[str(sent.uuid)]["has_json"])
        self.assertFalse(rows[str(processing.uuid)]["has_json"])

    def test_invalid_status_is_rejected_with_400(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )

        response = self._request(
            project_uuid=self.project.uuid, query_string="statuses=bogus"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_template_uuid_is_rejected_with_400(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )

        response = self._request(
            project_uuid=self.project.uuid, query_string="template_uuids=not-a-uuid"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_template_metadata_is_resolved_from_parent_when_no_display_name(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        parent = PreApprovedTemplate.objects.create(
            agent=self.agent,
            slug="parent-slug",
            uuid=uuid4(),
            name="raw_parent",
            display_name="Parent Display",
            start_condition="x",
        )
        template = Template.objects.create(
            uuid=uuid4(),
            name="raw_template_name",
            integrated_agent=self.integrated_agent,
            parent=parent,
        )
        self._make_execution(template=template)

        response = self._request(project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.json()["results"][0]
        self.assertEqual(row["template_uuid"], str(template.uuid))
        self.assertEqual(row["template_name"], "Parent Display")

    def test_pagination_echoes_requested_values(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        for _ in range(3):
            self._make_execution()

        response = self._request(
            project_uuid=self.project.uuid,
            query_string="page=2&page_size=2",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["pagination"]["page"], 2)
        self.assertEqual(body["pagination"]["page_size"], 2)
        self.assertEqual(body["pagination"]["total"], 3)
        self.assertEqual(len(body["results"]), 1)

    def test_unknown_agent_returns_404(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        url = reverse("agent-logs", kwargs={"agent_uuid": str(uuid4())})

        response = self.client.get(
            url,
            HTTP_PROJECT_UUID=str(self.project.uuid),
            HTTP_AUTHORIZATION="Bearer x",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def _make_broadcast_message(self, broadcast_status: str) -> BroadcastMessage:
        return BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            status=broadcast_status,
        )

    def test_status_field_reflects_courier_delivered_state(self):
        """The log status surfaces ``delivered`` when the linked
        BroadcastMessage has been advanced past dispatch by the courier."""
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        broadcast_message = self._make_broadcast_message(BroadcastStatus.DELIVERED)
        self._make_execution(
            status=AgentExecutionStatus.SUCCESS,
            broadcast_message=broadcast_message,
        )

        response = self._request(project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.json()["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "delivered")

    def test_status_field_reflects_courier_read_state(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        broadcast_message = self._make_broadcast_message(BroadcastStatus.READ)
        self._make_execution(
            status=AgentExecutionStatus.SUCCESS,
            broadcast_message=broadcast_message,
        )

        response = self._request(project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.json()["results"]
        self.assertEqual(rows[0]["status"], "read")
