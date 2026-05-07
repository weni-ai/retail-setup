"""End-to-end tests for ``GET /assigneds/{agent_uuid}/logs/``.

These tests exercise the view: query parsing, permission checks,
response shape, status mapping, the ``json_url`` rules, and filter
forwarding to the use case.
"""

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.views import AgentLogsView
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
from retail.services.aws_s3.service import S3Service
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
        self.client.force_authenticate(self.user)

        self.url = reverse(
            "agent-logs", kwargs={"agent_uuid": str(self.integrated_agent.uuid)}
        )

    def _request(
        self, project_uuid=None, query_string: str = "", auth_token: str = "Bearer x"
    ):
        url = self.url + (f"?{query_string}" if query_string else "")
        headers = {}
        if project_uuid is not None:
            headers["HTTP_PROJECT_UUID"] = str(project_uuid)
        if auth_token:
            headers["HTTP_AUTHORIZATION"] = auth_token
        return self.client.get(url, **headers)

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
        self.assertIsNone(row["json_url"])

    @patch("retail.agents.domains.agent_execution.views.S3Service")
    def test_json_url_is_generated_for_skipped_and_error(self, mock_s3_class):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        mock_s3 = mock_s3_class.return_value
        mock_s3.generate_presigned_url.return_value = (
            "https://s3.amazonaws.com/test/payload.json?signed=yes"
        )

        skipped = self._make_execution(
            status=AgentExecutionStatus.SKIP,
            traces_s3_key="executions/skipped/traces.json",
        )
        errored = self._make_execution(
            status=AgentExecutionStatus.ERROR,
            traces_s3_key="executions/error/traces.json",
        )
        sent = self._make_execution(
            status=AgentExecutionStatus.SUCCESS,
            traces_s3_key="executions/sent/traces.json",
        )

        with self.settings(EXECUTION_TRACES_BUCKET="test-traces"):
            response = self._request(project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = {r["uuid"]: r for r in response.json()["results"]}

        self.assertEqual(
            rows[str(skipped.uuid)]["json_url"],
            "https://s3.amazonaws.com/test/payload.json?signed=yes",
        )
        self.assertEqual(
            rows[str(errored.uuid)]["json_url"],
            "https://s3.amazonaws.com/test/payload.json?signed=yes",
        )
        self.assertIsNone(rows[str(sent.uuid)]["json_url"])

    def test_search_filter_is_forwarded(self):
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        match = self._make_execution(contact_urn="whatsapp:+5511777777777")
        self._make_execution(contact_urn="whatsapp:+5511222222222")

        response = self._request(
            project_uuid=self.project.uuid, query_string="search=777777"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["uuid"], str(match.uuid))

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

    def test_status_filter_delivered_returns_only_delivered_rows(self):
        """End-to-end: a query for ``statuses=delivered`` joins through
        BroadcastMessage and returns only the rows whose courier
        lifecycle has reached DELIVERED."""
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        delivered = self._make_execution(
            status=AgentExecutionStatus.SUCCESS,
            broadcast_message=self._make_broadcast_message(BroadcastStatus.DELIVERED),
        )
        # Other rows that should NOT match the delivered filter.
        self._make_execution(
            status=AgentExecutionStatus.SUCCESS,
            broadcast_message=self._make_broadcast_message(BroadcastStatus.READ),
        )
        self._make_execution(
            status=AgentExecutionStatus.SUCCESS,
            broadcast_message=self._make_broadcast_message(BroadcastStatus.SENT),
        )
        self._make_execution(status=AgentExecutionStatus.SUCCESS)

        response = self._request(
            project_uuid=self.project.uuid, query_string="statuses=delivered"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.json()["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["uuid"], str(delivered.uuid))
        self.assertEqual(rows[0]["status"], "delivered")

    def test_status_filter_error_includes_courier_failed_dispatches(self):
        """``statuses=error`` covers both internal errors AND successful
        dispatches whose courier lifecycle terminated in FAILED."""
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(2)
        )
        internal_error = self._make_execution(
            status=AgentExecutionStatus.ERROR,
        )
        courier_failed = self._make_execution(
            status=AgentExecutionStatus.SUCCESS,
            broadcast_message=self._make_broadcast_message(BroadcastStatus.FAILED),
        )
        # Transient ERRORED stays in the ``sent`` bucket so the UI
        # doesn't flap when the courier retry succeeds.
        self._make_execution(
            status=AgentExecutionStatus.SUCCESS,
            broadcast_message=self._make_broadcast_message(BroadcastStatus.ERRORED),
        )

        response = self._request(
            project_uuid=self.project.uuid, query_string="statuses=error"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.json()["results"]
        returned_uuids = {row["uuid"] for row in rows}
        self.assertEqual(
            returned_uuids,
            {str(internal_error.uuid), str(courier_failed.uuid)},
        )


class BuildS3ServiceTests(SimpleTestCase):
    """Defensive branches for ``AgentLogsView._build_s3_service``.

    The helper deliberately swallows every failure (no bucket
    configured, broken S3 init) so the list endpoint never 500s just
    because traces storage is unreachable — the serializer already
    falls back to ``json_url=null`` in that case. These tests pin each
    of the three exit points.
    """

    @override_settings(EXECUTION_TRACES_BUCKET="", AWS_STORAGE_BUCKET_NAME="")
    def test_returns_none_when_both_bucket_settings_are_empty(self):
        self.assertIsNone(AgentLogsView._build_s3_service())

    @override_settings(EXECUTION_TRACES_BUCKET="traces-bucket")
    @patch("retail.agents.domains.agent_execution.views.S3Service")
    def test_returns_none_when_s3_service_constructor_raises(self, mock_s3_class):
        mock_s3_class.side_effect = RuntimeError("boto init failed")

        result = AgentLogsView._build_s3_service()

        self.assertIsNone(result)
        mock_s3_class.assert_called_once_with(bucket_name="traces-bucket")

    @override_settings(EXECUTION_TRACES_BUCKET="traces-bucket")
    @patch("retail.agents.domains.agent_execution.views.S3Service")
    def test_returns_s3_service_bound_to_configured_bucket(self, mock_s3_class):
        result = AgentLogsView._build_s3_service()

        self.assertIs(result, mock_s3_class.return_value)
        mock_s3_class.assert_called_once_with(bucket_name="traces-bucket")

    @override_settings(
        EXECUTION_TRACES_BUCKET="", AWS_STORAGE_BUCKET_NAME="fallback-bucket"
    )
    @patch("retail.agents.domains.agent_execution.views.S3Service")
    def test_falls_back_to_aws_storage_bucket_name_when_traces_bucket_is_empty(
        self, mock_s3_class
    ):
        result = AgentLogsView._build_s3_service()

        self.assertIs(result, mock_s3_class.return_value)
        mock_s3_class.assert_called_once_with(bucket_name="fallback-bucket")

    @override_settings(EXECUTION_TRACES_BUCKET="traces-bucket")
    @patch("retail.clients.aws_s3.client.boto3")
    def test_returns_real_s3_service_instance_when_constructor_succeeds(
        self, mock_boto3
    ):
        # Unlike the patched-class tests above, this one pins that the
        # happy path actually yields an ``S3Service``. ``boto3`` is
        # patched so ``S3Client`` construction doesn't touch AWS
        # credentials lookup on the test runner.
        result = AgentLogsView._build_s3_service()

        self.assertIsInstance(result, S3Service)
        self.assertEqual(result.client.bucket_name, "traces-bucket")
