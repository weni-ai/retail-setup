"""Simulate PIX recovery routing from the hub hook to the origin store."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.payment_recovery import (
    PaymentRecoveryWebhookUseCase,
)
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.tests.fakes import FakeVtexIOClient


PAYMENT_RECOVERY_AGENT_UUID = uuid4()
HUB_ACCOUNT = "columbiamx"
ORIGIN_ACCOUNT = "martimx"
ORDER_ID = "v123-01"


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "payment-recovery-subaccount-routing-tests",
        }
    },
    PAYMENT_RECOVERY_AGENT_UUID=str(PAYMENT_RECOVERY_AGENT_UUID),
)
class PaymentRecoverySubaccountRoutingTest(TestCase):
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
            uuid=PAYMENT_RECOVERY_AGENT_UUID,
            name="Payment Recovery",
            slug="payment-recovery",
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
            config={"payment_recovery": {"hook_created": True}},
        )
        self.origin_agent = IntegratedAgent.objects.create(
            agent=official_agent,
            project=self.origin,
            channel_uuid=uuid4(),
            is_active=True,
            config={"payment_recovery": {"hook_created": True}},
        )
        self.webhook_data = {
            "OrderId": ORDER_ID,
            "State": "payment-pending",
            "CurrentChange": "2026-08-19T00:00:00Z",
            "LastChange": "2026-08-19T00:00:00Z",
        }
        self.oms_client = FakeVtexIOClient(hostname=HUB_ACCOUNT, order_id=ORDER_ID)
        self.use_case = PaymentRecoveryWebhookUseCase(
            vtex_io_service=VtexIOService(client=self.oms_client),
            exec_logger=MagicMock(),
        )

    def _oms_hostname(self, hostname: str) -> None:
        self.oms_client.hostname = hostname

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery."
        "AgentOrderStatusUpdateUsecase.execute"
    )
    def test_dispatches_origin_store_agent_when_hostname_is_subaccount(
        self, mock_execute
    ):
        self._oms_hostname(ORIGIN_ACCOUNT)

        result = self.use_case.process_webhook_notification(
            self.ingress_agent, self.webhook_data
        )

        self.assertEqual(result["status"], "success")
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

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery."
        "AgentOrderStatusUpdateUsecase.execute"
    )
    def test_keeps_ingress_agent_when_hostname_matches_ingress_account(
        self, mock_execute
    ):
        self._oms_hostname(HUB_ACCOUNT)

        self.use_case.process_webhook_notification(
            self.ingress_agent, self.webhook_data
        )

        dispatched_agent, dto = mock_execute.call_args.args
        self.assertEqual(dispatched_agent.uuid, self.ingress_agent.uuid)
        self.assertEqual(dto.vtexAccount, HUB_ACCOUNT)

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery."
        "AgentOrderStatusUpdateUsecase.execute"
    )
    def test_falls_back_to_ingress_agent_when_origin_has_no_payment_recovery(
        self, mock_execute
    ):
        self.origin_agent.is_active = False
        self.origin_agent.save(update_fields=["is_active"])
        self._oms_hostname(ORIGIN_ACCOUNT)

        self.use_case.process_webhook_notification(
            self.ingress_agent, self.webhook_data
        )

        dispatched_agent, dto = mock_execute.call_args.args
        self.assertEqual(dispatched_agent.uuid, self.ingress_agent.uuid)
        self.assertEqual(dto.vtexAccount, HUB_ACCOUNT)
