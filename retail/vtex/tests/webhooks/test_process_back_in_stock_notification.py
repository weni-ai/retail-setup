import uuid
from unittest.mock import MagicMock

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project
from retail.webhooks.vtex.usecases.dto import ProcessBackInStockNotificationDTO
from retail.webhooks.vtex.usecases.exceptions import BackInStockSendNotReadyError
from retail.webhooks.vtex.usecases.process_back_in_stock_notification import (
    DISCARD_AGENT_INACTIVE,
    NOTIFICATION_SENT,
    ProcessBackInStockNotificationUseCase,
)


BACK_IN_STOCK_AGENT_UUID = str(uuid.uuid4())
LAMBDA_PAYLOAD = {
    "sku_id": "9",
    "client_name": "Maria Silva",
    "phone_number": "5511999887766",
    "store": "https://test-account.myvtex.com",
}


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "process-back-in-stock-notification-tests",
        }
    },
    BACK_IN_STOCK_AGENT_UUID=BACK_IN_STOCK_AGENT_UUID,
)
class ProcessBackInStockNotificationUseCaseTest(TestCase):
    def setUp(self):
        cache.clear()
        self.project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Test store",
            vtex_account="test-account",
        )
        self.agent = Agent.objects.create(
            uuid=BACK_IN_STOCK_AGENT_UUID,
            name="Back in stock",
            slug="back_in_stock",
            description="Back in stock agent",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid.uuid4(),
            agent=self.agent,
            project=self.project,
        )
        self.dto = ProcessBackInStockNotificationDTO(
            sku_id="9",
            phone="5511999887766",
            name="Maria Silva",
            locale="pt-BR",
        )
        self.execution_uuid = uuid.uuid4()
        self.mock_webhook = MagicMock()
        self.mock_webhook.execute_from_task.return_value = {"template": "back_in_stock"}
        self.mock_exec_logger = MagicMock()
        self.mock_exec_logger.log_webhook_received.return_value = self.execution_uuid

    def tearDown(self):
        cache.clear()

    def _use_case(self) -> ProcessBackInStockNotificationUseCase:
        return ProcessBackInStockNotificationUseCase(
            account="test-account",
            exec_logger=self.mock_exec_logger,
            agent_webhook=self.mock_webhook,
        )

    def test_discards_when_project_is_missing(self):
        result = ProcessBackInStockNotificationUseCase.from_vtex_account(
            "missing-account"
        ).execute(self.dto)

        self.assertTrue(result.discarded)
        self.assertEqual(result.reason, DISCARD_AGENT_INACTIVE)
        self.mock_webhook.execute_from_task.assert_not_called()

    def test_discards_when_agent_is_inactive(self):
        self.integrated_agent.is_active = False
        self.integrated_agent.save(update_fields=["is_active"])

        result = self._use_case().execute(self.dto)

        self.assertTrue(result.discarded)
        self.assertEqual(result.reason, DISCARD_AGENT_INACTIVE)
        self.mock_webhook.execute_from_task.assert_not_called()

    def test_discards_when_agent_uuid_is_not_configured(self):
        with self.settings(BACK_IN_STOCK_AGENT_UUID=""):
            result = self._use_case().execute(self.dto)

        self.assertTrue(result.discarded)
        self.assertEqual(result.reason, DISCARD_AGENT_INACTIVE)
        self.mock_webhook.execute_from_task.assert_not_called()

    def test_sends_minimum_lambda_payload_when_agent_is_active(self):
        result = self._use_case().execute(self.dto)

        self.assertFalse(result.discarded)
        self.assertEqual(result.reason, NOTIFICATION_SENT)
        self.mock_exec_logger.log_webhook_received.assert_called_once_with(
            integrated_agent=self.integrated_agent,
            payload=LAMBDA_PAYLOAD,
            contact_urn="whatsapp:5511999887766",
        )
        self.mock_webhook.execute_from_task.assert_called_once_with(
            integrated_agent_uuid=str(self.integrated_agent.uuid),
            payload=LAMBDA_PAYLOAD,
            params={},
            forwarded_execution_uuid=self.execution_uuid,
        )

    def test_sends_project_store_when_vtex_host_store_is_set(self):
        self.project.config = {"vtex_host_store": "https://www.loja.com.br/"}
        self.project.save(update_fields=["config"])

        with self.assertLogs(
            "retail.webhooks.vtex.usecases.process_back_in_stock_notification",
            level="INFO",
        ) as logs:
            self._use_case().execute(self.dto)

        payload = self.mock_webhook.execute_from_task.call_args.kwargs["payload"]
        self.assertEqual(payload["store"], "https://www.loja.com.br")
        self.assertNotIn("Store was not defined on the project", " ".join(logs.output))

    def test_logs_when_sending_default_store(self):
        with self.assertLogs(
            "retail.webhooks.vtex.usecases.process_back_in_stock_notification",
            level="INFO",
        ) as logs:
            self._use_case().execute(self.dto)

        combined = " ".join(logs.output)
        self.assertIn("Store was not defined on the project", combined)
        self.assertIn("sending the default for this agent", combined)
        self.assertIn("store=https://test-account.myvtex.com", combined)
        self.assertNotIn("5511999887766", combined)

    def test_raises_when_lambda_does_not_dispatch(self):
        self.mock_webhook.execute_from_task.return_value = None

        with self.assertRaises(BackInStockSendNotReadyError):
            self._use_case().execute(self.dto)

    def test_raises_when_lambda_call_fails(self):
        self.mock_webhook.execute_from_task.side_effect = RuntimeError("lambda down")

        with self.assertRaises(BackInStockSendNotReadyError):
            self._use_case().execute(self.dto)

    def test_does_not_log_phone(self):
        with self.assertLogs(
            "retail.webhooks.vtex.usecases.process_back_in_stock_notification",
            level="INFO",
        ) as logs:
            self._use_case().execute(self.dto)

        combined = " ".join(logs.output)
        self.assertNotIn("5511999887766", combined)
        self.assertIn("sku_id=9", combined)
