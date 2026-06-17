from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.payment_recovery import (
    PaymentRecoveryWebhookUseCase,
    DEFAULT_DELAY_MINUTES,
)


class PaymentRecoveryWebhookUseCaseTest(TestCase):
    def setUp(self):
        self.use_case = PaymentRecoveryWebhookUseCase()
        self.agent_uuid = uuid4()
        self.mock_integrated_agent = MagicMock(spec=IntegratedAgent)
        self.mock_integrated_agent.uuid = self.agent_uuid
        self.mock_integrated_agent.project.vtex_account = "testaccount"
        self.mock_integrated_agent.config = {
            "payment_recovery": {
                "webhook_url": "https://example.com/webhook/",
                "hook_created": True,
            }
        }
        self.webhook_data = {
            "OrderId": "v1234567-01",
            "State": "payment-pending",
            "CurrentChange": "2026-04-10T12:00:00Z",
            "LastChange": "2026-04-10T11:00:00Z",
        }

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery.IntegratedAgent"
    )
    def test_get_integrated_agent_found(self, mock_model):
        mock_model.objects.get.return_value = self.mock_integrated_agent
        result = self.use_case.get_integrated_agent(self.agent_uuid)
        self.assertEqual(result, self.mock_integrated_agent)
        mock_model.objects.get.assert_called_once_with(uuid=self.agent_uuid)

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery.IntegratedAgent"
    )
    def test_get_integrated_agent_not_found(self, mock_model):
        mock_model.DoesNotExist = IntegratedAgent.DoesNotExist
        mock_model.objects.get.side_effect = IntegratedAgent.DoesNotExist
        with self.assertRaises(NotFound):
            self.use_case.get_integrated_agent(self.agent_uuid)

    def test_validate_payment_recovery_enabled_succeeds(self):
        self.use_case.validate_payment_recovery_enabled(self.mock_integrated_agent)

    def test_validate_payment_recovery_disabled_raises(self):
        self.mock_integrated_agent.config = {
            "payment_recovery": {"hook_created": False}
        }
        with self.assertRaises(ValidationError):
            self.use_case.validate_payment_recovery_enabled(self.mock_integrated_agent)

    def test_validate_payment_recovery_missing_config_raises(self):
        self.mock_integrated_agent.config = {}
        with self.assertRaises(ValidationError):
            self.use_case.validate_payment_recovery_enabled(self.mock_integrated_agent)

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery.AgentOrderStatusUpdateUsecase"
    )
    def test_process_webhook_notification_success(self, mock_order_usecase_cls):
        mock_order_usecase = MagicMock()
        mock_order_usecase_cls.return_value = mock_order_usecase

        result = self.use_case.process_webhook_notification(
            self.mock_integrated_agent, self.webhook_data
        )

        self.assertEqual(result["status"], "success")
        mock_order_usecase.execute.assert_called_once()

        call_args = mock_order_usecase.execute.call_args
        dto = call_args[0][1]
        self.assertEqual(dto.orderId, "v1234567-01")
        self.assertEqual(dto.currentState, "payment-pending")
        self.assertEqual(dto.vtexAccount, "testaccount")

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery.AgentOrderStatusUpdateUsecase"
    )
    def test_process_webhook_notification_without_minimum_skips_value_lookup(
        self, mock_order_usecase_cls
    ):
        """No minimum configured: dispatch happens without querying VTEX."""
        mock_vtex_io = MagicMock()
        use_case = PaymentRecoveryWebhookUseCase(vtex_io_service=mock_vtex_io)

        result = use_case.process_webhook_notification(
            self.mock_integrated_agent, self.webhook_data
        )

        self.assertEqual(result["status"], "success")
        mock_vtex_io.get_order_details_by_id.assert_not_called()
        mock_order_usecase_cls.return_value.execute.assert_called_once()

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery.AgentOrderStatusUpdateUsecase"
    )
    def test_process_webhook_notification_skipped_below_minimum(
        self, mock_order_usecase_cls
    ):
        """Order value below the configured minimum skips the dispatch."""
        self.mock_integrated_agent.config["payment_recovery"][
            "minimum_order_value"
        ] = 100.0
        mock_vtex_io = MagicMock()
        # VTEX returns value in cents: 5000 = R$ 50,00 < R$ 100,00
        mock_vtex_io.get_order_details_by_id.return_value = {"value": 5000}
        use_case = PaymentRecoveryWebhookUseCase(vtex_io_service=mock_vtex_io)

        result = use_case.process_webhook_notification(
            self.mock_integrated_agent, self.webhook_data
        )

        self.assertEqual(result["status"], "skipped")
        mock_order_usecase_cls.return_value.execute.assert_not_called()
        mock_vtex_io.get_order_details_by_id.assert_called_once()

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery.AgentOrderStatusUpdateUsecase"
    )
    def test_process_webhook_notification_dispatches_when_value_meets_minimum(
        self, mock_order_usecase_cls
    ):
        """Order value at/above the minimum dispatches the recovery."""
        self.mock_integrated_agent.config["payment_recovery"][
            "minimum_order_value"
        ] = 100.0
        mock_vtex_io = MagicMock()
        # 15000 cents = R$ 150,00 >= R$ 100,00
        mock_vtex_io.get_order_details_by_id.return_value = {"value": 15000}
        use_case = PaymentRecoveryWebhookUseCase(vtex_io_service=mock_vtex_io)

        result = use_case.process_webhook_notification(
            self.mock_integrated_agent, self.webhook_data
        )

        self.assertEqual(result["status"], "success")
        mock_order_usecase_cls.return_value.execute.assert_called_once()

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery.AgentOrderStatusUpdateUsecase"
    )
    def test_process_webhook_notification_dispatches_when_value_unresolved(
        self, mock_order_usecase_cls
    ):
        """A VTEX lookup failure does not drop a legitimate recovery."""
        self.mock_integrated_agent.config["payment_recovery"][
            "minimum_order_value"
        ] = 100.0
        mock_vtex_io = MagicMock()
        mock_vtex_io.get_order_details_by_id.side_effect = Exception("boom")
        use_case = PaymentRecoveryWebhookUseCase(vtex_io_service=mock_vtex_io)

        result = use_case.process_webhook_notification(
            self.mock_integrated_agent, self.webhook_data
        )

        self.assertEqual(result["status"], "success")
        mock_order_usecase_cls.return_value.execute.assert_called_once()

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery.AgentOrderStatusUpdateUsecase"
    )
    def test_process_webhook_notification_disabled_raises(self, mock_order_usecase_cls):
        self.mock_integrated_agent.config = {}

        with self.assertRaises(ValidationError):
            self.use_case.process_webhook_notification(
                self.mock_integrated_agent, self.webhook_data
            )

        mock_order_usecase_cls.return_value.execute.assert_not_called()

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery.IntegratedAgent"
    )
    def test_get_delay_seconds_from_config(self, mock_model):
        self.mock_integrated_agent.config = {"payment_recovery": {"delay_minutes": 15}}
        mock_model.objects.get.return_value = self.mock_integrated_agent

        result = self.use_case.get_delay_seconds(self.agent_uuid)

        self.assertEqual(result, 15 * 60)

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery.IntegratedAgent"
    )
    def test_get_delay_seconds_uses_default_when_not_configured(self, mock_model):
        self.mock_integrated_agent.config = {"payment_recovery": {}}
        mock_model.objects.get.return_value = self.mock_integrated_agent

        result = self.use_case.get_delay_seconds(self.agent_uuid)

        self.assertEqual(result, DEFAULT_DELAY_MINUTES * 60)

    @patch(
        "retail.agents.domains.agent_integration.usecases.payment_recovery.IntegratedAgent"
    )
    def test_get_delay_seconds_uses_default_when_agent_not_found(self, mock_model):
        mock_model.DoesNotExist = IntegratedAgent.DoesNotExist
        mock_model.objects.get.side_effect = IntegratedAgent.DoesNotExist

        result = self.use_case.get_delay_seconds(self.agent_uuid)

        self.assertEqual(result, DEFAULT_DELAY_MINUTES * 60)

    def test_get_order_value_returns_none_when_order_id_missing(self):
        mock_vtex_io = MagicMock()
        use_case = PaymentRecoveryWebhookUseCase(vtex_io_service=mock_vtex_io)

        self.assertIsNone(use_case._get_order_value(None, "testaccount"))
        mock_vtex_io.get_order_details_by_id.assert_not_called()

    def test_get_order_value_returns_none_when_order_details_empty(self):
        mock_vtex_io = MagicMock()
        mock_vtex_io.get_order_details_by_id.return_value = {}
        use_case = PaymentRecoveryWebhookUseCase(vtex_io_service=mock_vtex_io)

        self.assertIsNone(use_case._get_order_value("v1234567-01", "testaccount"))

    def test_get_order_value_returns_none_when_value_absent(self):
        mock_vtex_io = MagicMock()
        mock_vtex_io.get_order_details_by_id.return_value = {"orderId": "v1234567-01"}
        use_case = PaymentRecoveryWebhookUseCase(vtex_io_service=mock_vtex_io)

        self.assertIsNone(use_case._get_order_value("v1234567-01", "testaccount"))

    def test_get_order_value_returns_none_when_value_invalid(self):
        mock_vtex_io = MagicMock()
        mock_vtex_io.get_order_details_by_id.return_value = {"value": "abc"}
        use_case = PaymentRecoveryWebhookUseCase(vtex_io_service=mock_vtex_io)

        self.assertIsNone(use_case._get_order_value("v1234567-01", "testaccount"))

    def test_get_order_value_converts_cents_to_major_units(self):
        from decimal import Decimal

        mock_vtex_io = MagicMock()
        mock_vtex_io.get_order_details_by_id.return_value = {"value": 2047}
        use_case = PaymentRecoveryWebhookUseCase(vtex_io_service=mock_vtex_io)

        self.assertEqual(
            use_case._get_order_value("v1234567-01", "testaccount"),
            Decimal("20.47"),
        )
