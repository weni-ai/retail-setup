"""End-to-end flow tests for VTEX order amount propagation into agent logs.

Unit tests mock ``ExecutionLoggerService``; these wire the real logger,
buffer, and flush pipeline so ``AgentExecution.amount`` / ``currency``
survive to Postgres and surface through the public list-API serializer.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.agents.domains.agent_execution.context import clear_execution_context
from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.serializers import AgentLogRowSerializer
from retail.agents.domains.agent_execution.services.buffer import (
    ExecutionBufferService,
)
from retail.agents.domains.agent_execution.services.logger import (
    ExecutionLoggerService,
)
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)
from retail.agents.domains.agent_execution.tests._fakes import (
    FakeRedisConnection,
    FakeS3Client,
)
from retail.agents.domains.agent_execution.usecases.flush_executions import (
    FlushExecutionsUseCase,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.payment_recovery import (
    PaymentRecoveryWebhookUseCase,
)
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.projects.models import Project
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


@override_settings(
    EXECUTION_TRACES_BUCKET="test-traces-bucket",
    ORDER_STATUS_DUPLICATE_WINDOW_SECONDS=60,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "order-amount-flow-tests",
        }
    },
)
class OrderAmountExecutionLogFlowTests(TestCase):
    """Logger → use case → buffer → flush → DB + API serializer."""

    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)
        cache.clear()

        self.fake_redis = FakeRedisConnection()
        self.fake_s3 = FakeS3Client(bucket_name="test-traces-bucket")
        self.traces_storage = ExecutionTracesStorageService(s3_service=self.fake_s3)

        patcher = patch(
            "retail.agents.domains.agent_execution.services.buffer."
            "get_redis_connection",
            return_value=self.fake_redis,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.buffer = ExecutionBufferService(traces_storage=self.traces_storage)
        self.exec_logger = ExecutionLoggerService(buffer_service=self.buffer)

        self.project = Project.objects.create(
            name="Flow Project", uuid=uuid4(), vtex_account="flowstore"
        )
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Order Status",
            slug="order-status",
            description="",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            config={
                "payment_recovery": {
                    "hook_created": True,
                    "minimum_order_value": 100.0,
                }
            },
        )
        self.mock_vtex_io = MagicMock()

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _flush(self) -> None:
        FlushExecutionsUseCase(
            buffer=self.buffer, traces_storage=self.traces_storage
        ).execute()

    def _order_status_dto(self) -> OrderStatusDTO:
        return OrderStatusDTO(
            recorder={},
            domain="Marketplace",
            orderId="1646748157477-01",
            currentState="payment-approved",
            lastState="payment-pending",
            currentChangeDate="2026-07-14T17:47:35.779879+00:00",
            lastChangeDate="2026-07-14T17:47:30.000000+00:00",
            vtexAccount=self.project.vtex_account,
        )

    @patch(
        "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase"
    )
    def test_order_status_flow_persists_amount_through_flush_and_api(
        self, mock_webhook_use_case_cls
    ):
        mock_webhook = MagicMock()
        mock_webhook_use_case_cls.return_value = mock_webhook
        mock_webhook._addapt_credentials.return_value = {}
        mock_webhook.execute.return_value = None

        self.mock_vtex_io.get_order_details_by_id.return_value = {
            "value": 3598,
            "storePreferencesData": {"currencyCode": "BRL"},
        }

        use_case = AgentOrderStatusUpdateUsecase(
            exec_logger=self.exec_logger,
            vtex_io_service=self.mock_vtex_io,
        )

        self.exec_logger.log_webhook_received(
            integrated_agent=self.integrated_agent,
            payload={"OrderId": "1646748157477-01"},
            order_id="1646748157477-01",
        )
        use_case.execute(self.integrated_agent, self._order_status_dto())
        self.exec_logger.log_execution_skip(reason="test_terminal_for_flush")

        self._flush()

        row = AgentExecution.objects.get(integrated_agent=self.integrated_agent)
        self.assertEqual(row.amount, Decimal("35.98"))
        self.assertEqual(row.currency, "BRL")
        self.assertEqual(row.status, AgentExecutionStatus.SKIP)

        api_row = AgentLogRowSerializer(row).data
        self.assertEqual(api_row["amount"], {"value": "35.98", "currency": "BRL"})
        mock_webhook.execute.assert_called_once()

    @patch(
        "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase"
    )
    def test_payment_recovery_success_reuses_single_vtex_lookup(
        self, mock_webhook_use_case_cls
    ):
        mock_webhook = MagicMock()
        mock_webhook_use_case_cls.return_value = mock_webhook
        mock_webhook._addapt_credentials.return_value = {}
        mock_webhook.execute.return_value = None

        self.mock_vtex_io.get_order_details_by_id.return_value = {
            "value": 15000,
            "storePreferencesData": {"currencyCode": "BRL"},
        }

        self.exec_logger.log_webhook_received(
            integrated_agent=self.integrated_agent,
            payload={"OrderId": "1646748157477-01"},
            order_id="1646748157477-01",
        )

        use_case = PaymentRecoveryWebhookUseCase(
            vtex_io_service=self.mock_vtex_io,
            exec_logger=self.exec_logger,
        )
        webhook_data = {
            "OrderId": "1646748157477-01",
            "State": "payment-pending",
            "CurrentChange": "2026-07-14T17:47:35.779879+00:00",
            "LastChange": "2026-07-14T17:47:30.000000+00:00",
        }
        result = use_case.process_webhook_notification(
            self.integrated_agent, webhook_data
        )

        self.assertEqual(result["status"], "success")
        self.mock_vtex_io.get_order_details_by_id.assert_called_once()
        self.exec_logger.log_execution_skip(reason="test_terminal_for_flush")
        self._flush()

        row = AgentExecution.objects.get(integrated_agent=self.integrated_agent)
        self.assertEqual(row.amount, Decimal("150.00"))
        self.assertEqual(row.currency, "BRL")

    def test_payment_recovery_minimum_skip_persists_amount_on_execution_row(self):
        self.mock_vtex_io.get_order_details_by_id.return_value = {
            "value": 5000,
            "storePreferencesData": {"currencyCode": "BRL"},
        }

        self.exec_logger.log_webhook_received(
            integrated_agent=self.integrated_agent,
            payload={"OrderId": "1646748157435-01"},
            order_id="1646748157435-01",
        )

        use_case = PaymentRecoveryWebhookUseCase(
            vtex_io_service=self.mock_vtex_io,
            exec_logger=self.exec_logger,
        )
        result = use_case.process_webhook_notification(
            self.integrated_agent,
            {
                "OrderId": "1646748157435-01",
                "State": "payment-pending",
            },
        )

        self.assertEqual(result["status"], "skipped")
        self._flush()

        row = AgentExecution.objects.get(integrated_agent=self.integrated_agent)
        self.assertEqual(row.amount, Decimal("50.00"))
        self.assertEqual(row.currency, "BRL")
        self.assertEqual(row.status, AgentExecutionStatus.SKIP)

        api_row = AgentLogRowSerializer(row).data
        self.assertEqual(api_row["amount"], {"value": "50.00", "currency": "BRL"})
        self.assertEqual(api_row["status"], "skipped")

    @patch(
        "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase"
    )
    def test_duplicate_skip_does_not_issue_second_vtex_lookup(
        self, mock_webhook_use_case_cls
    ):
        """First event fetches VTEX once; the duplicate short-circuit must not."""
        use_case = AgentOrderStatusUpdateUsecase(
            exec_logger=self.exec_logger,
            vtex_io_service=self.mock_vtex_io,
        )

        self.exec_logger.log_webhook_received(
            integrated_agent=self.integrated_agent,
            payload={"OrderId": "order-id"},
            order_id="order-id",
        )

        dto = OrderStatusDTO(
            recorder={},
            domain="Marketplace",
            orderId="order-id",
            currentState="invoiced",
            lastState="payment-approved",
            currentChangeDate="2026-07-14T00:00:00+00:00",
            lastChangeDate="2026-07-14T00:00:00+00:00",
            vtexAccount=self.project.vtex_account,
        )
        use_case.execute(self.integrated_agent, dto)
        use_case.execute(self.integrated_agent, dto)

        self.mock_vtex_io.get_order_details_by_id.assert_called_once()
        mock_webhook_use_case_cls.return_value.execute.assert_called_once()
