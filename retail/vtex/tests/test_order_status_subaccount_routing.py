"""Simulate order-status routing from the hub account to the origin store."""

from unittest.mock import patch
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.tests.fakes import FakeVtexIOClient


ORDER_STATUS_AGENT_UUID = uuid4()
HUB_ACCOUNT = "columbiamx"
ORIGIN_ACCOUNT = "martimx"
ORDER_ID = "v123-01"


def _order_update_data(vtex_account: str = HUB_ACCOUNT) -> dict:
    return {
        "recorder": {},
        "domain": "Marketplace",
        "orderId": ORDER_ID,
        "currentState": "ready-for-handling",
        "lastState": "payment-approved",
        "currentChangeDate": "2026-08-19T00:00:00Z",
        "lastChangeDate": "2026-08-19T00:00:00Z",
        "vtexAccount": vtex_account,
    }


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "order-status-subaccount-routing-tests",
        }
    },
    ORDER_STATUS_AGENT_UUID=str(ORDER_STATUS_AGENT_UUID),
)
class OrderStatusSubaccountRoutingTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

        self.hub = Project.objects.create(
            uuid=uuid4(),
            name="Columbia",
            vtex_account=HUB_ACCOUNT,
            config={
                "vtex_config": {
                    "vtex_sub_accounts": [HUB_ACCOUNT, ORIGIN_ACCOUNT, "diablosrojosmx"]
                }
            },
        )
        self.origin = Project.objects.create(
            uuid=uuid4(),
            name="Marti",
            vtex_account=ORIGIN_ACCOUNT,
        )
        official_agent = Agent.objects.create(
            uuid=ORDER_STATUS_AGENT_UUID,
            name="Order Status",
            slug="order-status",
            description="official",
            lambda_arn="arn:aws:lambda:fake",
            project=self.hub,
            is_oficial=True,
            credentials={},
        )
        self.ingress_agent = IntegratedAgent.objects.create(
            agent=official_agent,
            project=self.hub,
            channel_uuid=uuid4(),
            is_active=True,
        )
        self.origin_agent = IntegratedAgent.objects.create(
            agent=official_agent,
            project=self.origin,
            channel_uuid=uuid4(),
            is_active=True,
        )

    def _vtex_io_with_oms(self, hostname: str) -> VtexIOService:
        self.oms_client = FakeVtexIOClient(hostname=hostname, order_id=ORDER_ID)
        return VtexIOService(client=self.oms_client)

    @patch("retail.vtex.tasks.task_mark_broadcast_converted")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    @patch.object(AgentOrderStatusUpdateUsecase, "execute")
    @patch("retail.vtex.usecases.resolve_order_origin_account.VtexIOService")
    def test_dispatches_origin_store_agent_when_hostname_is_subaccount(
        self, mock_vtex_io_cls, mock_execute, _mock_logger_factory, _mock_conversion
    ):
        from retail.vtex.tasks import task_order_status_update

        mock_vtex_io_cls.return_value = self._vtex_io_with_oms(ORIGIN_ACCOUNT)

        task_order_status_update(_order_update_data())

        mock_execute.assert_called_once()
        dispatched_agent, dto = mock_execute.call_args.args
        self.assertEqual(dispatched_agent.uuid, self.origin_agent.uuid)
        self.assertEqual(dispatched_agent.project_id, self.origin.id)
        self.assertEqual(dto.vtexAccount, ORIGIN_ACCOUNT)
        self.assertEqual(
            self.oms_client.proxy_calls,
            [
                {
                    "account_domain": f"{HUB_ACCOUNT}.myvtex.com",
                    "vtex_account": HUB_ACCOUNT,
                    "method": "GET",
                    "path": f"/api/oms/pvt/orders/{ORDER_ID}",
                }
            ],
        )

    @patch("retail.vtex.tasks.task_mark_broadcast_converted")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    @patch.object(AgentOrderStatusUpdateUsecase, "execute")
    @patch("retail.vtex.usecases.resolve_order_origin_account.VtexIOService")
    def test_keeps_ingress_agent_when_hostname_matches_ingress_account(
        self, mock_vtex_io_cls, mock_execute, _mock_logger_factory, _mock_conversion
    ):
        from retail.vtex.tasks import task_order_status_update

        mock_vtex_io_cls.return_value = self._vtex_io_with_oms(HUB_ACCOUNT)

        task_order_status_update(_order_update_data())

        mock_execute.assert_called_once()
        dispatched_agent, dto = mock_execute.call_args.args
        self.assertEqual(dispatched_agent.uuid, self.ingress_agent.uuid)
        self.assertEqual(dto.vtexAccount, HUB_ACCOUNT)
