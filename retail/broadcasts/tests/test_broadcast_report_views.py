"""End-to-end tests for broadcast report APIs."""

from decimal import Decimal
from uuid import uuid4

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.broadcasts.models import (
    BroadcastConversion,
    BroadcastMessage,
    BroadcastStatus,
)
from retail.internal.test_mixins import BaseTestMixin, with_test_settings
from retail.projects.models import Project


User = get_user_model()
PAYMENT_RECOVERY_AGENT_UUID = str(uuid4())


@with_test_settings
class BroadcastReportViewsTest(BaseTestMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.setup_connect_service_mock(
            status_code=200,
            permissions={"project_authorization": 2},
        )

        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.other_project = Project.objects.create(name="Project B", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent",
            slug="agent",
            description="",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )
        self.second_integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )
        self.other_integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.other_project,
            channel_uuid=uuid4(),
        )

        self.user = User.objects.create_user(
            username="tester",
            password="x",
            email="tester@example.com",
        )
        self.client.force_authenticate(self.user)

        self.project_dispatches_url = reverse("broadcast-project-dispatches")
        self.project_summary_url = reverse("broadcast-project-summary")
        self.agent_dispatches_url = reverse(
            "broadcast-agent-dispatches",
            kwargs={"agent_uuid": str(self.integrated_agent.uuid)},
        )
        self.summary_url = reverse(
            "broadcast-agent-summary",
            kwargs={"agent_uuid": str(self.integrated_agent.uuid)},
        )
        today = timezone.localdate()
        start_date = today - timedelta(days=1)
        end_date = today + timedelta(days=1)
        self.query = (
            f"start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
        )

    def _get(self, url, *, project_uuid=None, query=None):
        headers = {"HTTP_AUTHORIZATION": "Bearer token"}
        if project_uuid is not None:
            headers["HTTP_PROJECT_UUID"] = str(project_uuid)
        full_url = url
        if query:
            full_url = f"{url}?{query}"
        return self.client.get(full_url, **headers)

    def test_project_dispatches_returns_report_rows(self):
        broadcast = BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            template_name="payment_recovery",
            contact_urn="whatsapp:5511888888888",
            status=BroadcastStatus.DELIVERED,
            order_id="order-99",
        )
        converted_at = timezone.now()
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            broadcast=broadcast,
            order_id="order-99",
            converted_at=converted_at,
        )

        response = self._get(
            self.project_dispatches_url,
            project_uuid=self.project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pagination"]["total"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["contact_urn"], "whatsapp:5511888888888")
        self.assertEqual(row["order_id"], "order-99")
        self.assertEqual(row["status"], BroadcastStatus.DELIVERED)
        self.assertTrue(row["converted"])
        self.assertIsNotNone(row["dispatched_at"])
        self.assertIsNotNone(row["converted_at"])

    def test_project_dispatches_requires_project_header(self):
        response = self._get(self.project_dispatches_url, query=self.query)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_project_dispatches_rejects_invalid_project_header(self):
        response = self._get(
            self.project_dispatches_url,
            project_uuid="not-a-valid-uuid",
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_summary_returns_delivered_and_converted_totals(self):
        BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            template_name="payment_recovery",
            contact_urn="whatsapp:5511777777777",
            status=BroadcastStatus.DELIVERED,
            order_id="order-1",
        )
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            order_id="order-1",
        )

        response = self._get(
            self.summary_url,
            project_uuid=self.project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["delivered"], 1)
        self.assertEqual(response.data["converted"], 1)

    def test_summary_rejects_agent_from_other_project(self):
        response = self._get(
            self.summary_url,
            project_uuid=self.other_project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_project_dispatches_rejects_invalid_date_range(self):
        response = self._get(
            self.project_dispatches_url,
            project_uuid=self.project.uuid,
            query="start_date=2026-06-30&end_date=2026-06-01",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_summary_returns_404_for_unknown_agent(self):
        unknown_url = reverse(
            "broadcast-agent-summary",
            kwargs={"agent_uuid": str(uuid4())},
        )

        response = self._get(
            unknown_url,
            project_uuid=self.project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_project_summary_returns_totals_for_all_agents(self):
        BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            template_name="payment_recovery",
            contact_urn="whatsapp:5511444444444",
            status=BroadcastStatus.DELIVERED,
            order_id="order-a",
        )
        BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.second_integrated_agent,
            template_name="payment_recovery",
            contact_urn="whatsapp:5511333333333",
            status=BroadcastStatus.READ,
            order_id="order-b",
        )
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            order_id="order-a",
        )
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.second_integrated_agent,
            order_id="order-b",
        )

        response = self._get(
            self.project_summary_url,
            project_uuid=self.project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["delivered"], 2)
        self.assertEqual(response.data["converted"], 2)

    def test_project_summary_requires_project_header(self):
        response = self._get(self.project_summary_url, query=self.query)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_agent_dispatches_returns_only_matching_agent_rows(self):
        BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            template_name="payment_recovery",
            contact_urn="whatsapp:5511666666666",
            status=BroadcastStatus.DELIVERED,
            order_id="order-agent",
        )
        BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.second_integrated_agent,
            template_name="payment_recovery",
            contact_urn="whatsapp:5511555555555",
            status=BroadcastStatus.DELIVERED,
            order_id="order-other-agent",
        )

        response = self._get(
            self.agent_dispatches_url,
            project_uuid=self.project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pagination"]["total"], 1)
        self.assertEqual(response.data["results"][0]["order_id"], "order-agent")

    def test_agent_dispatches_rejects_agent_from_other_project(self):
        response = self._get(
            self.agent_dispatches_url,
            project_uuid=self.other_project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_agent_dispatches_returns_404_for_unknown_agent(self):
        unknown_url = reverse(
            "broadcast-agent-dispatches",
            kwargs={"agent_uuid": str(uuid4())},
        )

        response = self._get(
            unknown_url,
            project_uuid=self.project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@with_test_settings
@override_settings(PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_AGENT_UUID)
class BroadcastPaymentRecoveryConversionViewsTest(BaseTestMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.setup_connect_service_mock(
            status_code=200,
            permissions={"project_authorization": 2},
        )

        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.other_project = Project.objects.create(name="Project B", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=PAYMENT_RECOVERY_AGENT_UUID,
            name="Whatsapp Payment Recovery",
            slug="payment-recovery",
            description="",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )
        self.second_integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )

        self.user = User.objects.create_user(
            username="payment-recovery-tester",
            password="x",
            email="payment-recovery@example.com",
        )
        self.client.force_authenticate(self.user)

        self.project_conversion_url = reverse(
            "broadcast-project-payment-recovery-conversion"
        )
        self.agent_conversion_url = reverse(
            "broadcast-agent-payment-recovery-conversion",
            kwargs={"agent_uuid": str(self.integrated_agent.uuid)},
        )
        today = timezone.localdate()
        start_date = today - timedelta(days=1)
        end_date = today + timedelta(days=1)
        self.query = (
            f"start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
        )

    def _get(self, url, *, project_uuid=None, query=None):
        headers = {"HTTP_AUTHORIZATION": "Bearer token"}
        if project_uuid is not None:
            headers["HTTP_PROJECT_UUID"] = str(project_uuid)
        full_url = url
        if query:
            full_url = f"{url}?{query}"
        return self.client.get(full_url, **headers)

    def test_project_payment_recovery_conversion_returns_metrics(self):
        broadcast = BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            template_name="payment_recovery",
            contact_urn="whatsapp:5511888888888",
            status=BroadcastStatus.DELIVERED,
            order_id="order-99",
        )
        BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            template_name="payment_recovery",
            contact_urn="whatsapp:5511777777777",
            status=BroadcastStatus.QUEUED,
            order_id="order-queued",
        )
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            broadcast=broadcast,
            order_id="order-99",
            value=Decimal("150.00"),
        )

        response = self._get(
            self.project_conversion_url,
            project_uuid=self.project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_dispatches"], 1)
        self.assertEqual(response.data["converted_payments"], 1)
        self.assertEqual(str(response.data["conversion_rate"]), "100.00")
        self.assertEqual(str(response.data["recovered_revenue"]), "150.00")
        self.assertEqual(str(response.data["average_ticket"]), "150.00")

    def test_project_payment_recovery_conversion_requires_project_header(self):
        response = self._get(self.project_conversion_url, query=self.query)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_agent_payment_recovery_conversion_returns_only_matching_agent_rows(self):
        broadcast = BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            template_name="payment_recovery",
            contact_urn="whatsapp:5511666666666",
            status=BroadcastStatus.SENT,
            order_id="order-agent",
        )
        BroadcastMessage.objects.create(
            project=self.project,
            integrated_agent=self.second_integrated_agent,
            template_name="payment_recovery",
            contact_urn="whatsapp:5511555555555",
            status=BroadcastStatus.SENT,
            order_id="order-other-agent",
        )
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            broadcast=broadcast,
            order_id="order-agent",
            value=Decimal("80.00"),
        )

        response = self._get(
            self.agent_conversion_url,
            project_uuid=self.project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_dispatches"], 1)
        self.assertEqual(response.data["converted_payments"], 1)
        self.assertEqual(str(response.data["recovered_revenue"]), "80.00")

    def test_agent_payment_recovery_conversion_rejects_agent_from_other_project(self):
        response = self._get(
            self.agent_conversion_url,
            project_uuid=self.other_project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_agent_payment_recovery_conversion_returns_404_for_unknown_agent(self):
        unknown_url = reverse(
            "broadcast-agent-payment-recovery-conversion",
            kwargs={"agent_uuid": str(uuid4())},
        )

        response = self._get(
            unknown_url,
            project_uuid=self.project.uuid,
            query=self.query,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
