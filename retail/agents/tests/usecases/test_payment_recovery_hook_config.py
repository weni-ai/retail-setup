from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.payment_recovery_hook_config import (
    PaymentRecoveryHookConfigUseCase,
)
from retail.agents.shared.cache import IntegratedAgentCacheHandler
from retail.projects.models import Project


class PaymentRecoveryHookConfigUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Test Project",
            vtex_account="teststore",
        )
        self.integrated_agent = MagicMock(spec=IntegratedAgent)
        self.integrated_agent.uuid = uuid4()
        self.integrated_agent.project = self.project
        self.integrated_agent.config = {
            "payment_recovery": {
                "hook_created": True,
                "webhook_url": "https://retail.example.com/webhook/",
                "sales_channels": ["1"],
            }
        }
        self.mock_proxy = MagicMock()
        self.mock_cache_handler = MagicMock(spec=IntegratedAgentCacheHandler)
        self.use_case = PaymentRecoveryHookConfigUseCase(
            proxy_vtex_usecase=self.mock_proxy,
            cache_handler=self.mock_cache_handler,
        )

    def test_get_hook_config_returns_stored_sales_channels(self):
        config = self.use_case.get_hook_config(self.integrated_agent)
        self.assertEqual(config["sales_channels"], ["1"])
        self.assertTrue(config["hook_created"])

    def test_get_hook_config_defaults_sales_channels_when_absent(self):
        self.integrated_agent.config = {"payment_recovery": {"hook_created": True}}
        config = self.use_case.get_hook_config(self.integrated_agent)
        self.assertEqual(config["sales_channels"], ["1"])

    def test_get_integrated_agent_not_found(self):
        with self.assertRaises(NotFound):
            self.use_case.get_integrated_agent(uuid4())

    def test_update_sales_channels_raises_when_hook_not_created(self):
        self.integrated_agent.config = {"payment_recovery": {"hook_created": False}}
        with self.assertRaises(ValidationError):
            self.use_case.update_sales_channels(self.integrated_agent, ["2"])

    def test_update_sales_channels_rejects_empty_channel_values(self):
        with self.assertRaises(ValidationError):
            self.use_case.update_sales_channels(self.integrated_agent, ["1", "  "])

    def test_normalize_sales_channels_allows_empty_list_for_all_channels(self):
        self.assertEqual(self.use_case._normalize_sales_channels([]), [])

    @override_settings(DOMAIN="https://retail.example.com")
    def test_update_sales_channels_syncs_vtex_hook_and_persists_config(self):
        config = self.use_case.update_sales_channels(
            self.integrated_agent, ["2", "3", "2"]
        )

        self.assertEqual(config["sales_channels"], ["2", "3"])
        self.assertEqual(
            self.integrated_agent.config["payment_recovery"]["sales_channels"],
            ["2", "3"],
        )
        self.integrated_agent.save.assert_called_once_with(update_fields=["config"])
        self.mock_cache_handler.invalidate_all_for.assert_called_once_with(
            self.integrated_agent
        )

        self.mock_proxy.execute.assert_called_once()
        call_kwargs = self.mock_proxy.execute.call_args[1]
        self.assertEqual(call_kwargs["method"], "POST")
        self.assertEqual(call_kwargs["path"], "/api/orders/hook/config")
        self.assertEqual(call_kwargs["project_uuid"], str(self.project.uuid))
        self.assertIn('salesChannel = "2"', call_kwargs["data"]["filter"]["expression"])
        self.assertIn('salesChannel = "3"', call_kwargs["data"]["filter"]["expression"])

    @override_settings(DOMAIN="https://retail.example.com")
    def test_update_sales_channels_with_empty_list_matches_all_channels_hook(self):
        self.use_case.update_sales_channels(self.integrated_agent, [])

        call_kwargs = self.mock_proxy.execute.call_args[1]
        self.assertEqual(
            call_kwargs["data"]["filter"]["expression"],
            "isCompleted = false and "
            'paymentData.transactions.payments[paymentSystem = "125"]',
        )
        self.assertEqual(
            self.integrated_agent.config["payment_recovery"]["sales_channels"],
            [],
        )

    def test_update_sales_channels_does_not_persist_when_vtex_sync_fails(self):
        self.mock_proxy.execute.side_effect = Exception("VTEX unavailable")

        with self.assertRaises(Exception):
            self.use_case.update_sales_channels(self.integrated_agent, ["2"])

        self.integrated_agent.save.assert_not_called()
        self.mock_cache_handler.invalidate_all_for.assert_not_called()

    @override_settings(DOMAIN="https://retail.example.com")
    def test_build_webhook_url_falls_back_to_domain_when_config_missing(self):
        self.integrated_agent.config["payment_recovery"].pop("webhook_url", None)

        self.use_case.update_sales_channels(self.integrated_agent, ["2"])

        call_kwargs = self.mock_proxy.execute.call_args[1]
        self.assertIn(
            f"payment-recovery-webhook/{self.integrated_agent.uuid}/",
            call_kwargs["data"]["hook"]["url"],
        )

    def test_lazy_proxy_usecase_initialization(self):
        use_case = PaymentRecoveryHookConfigUseCase()
        self.assertIsNotNone(use_case._get_proxy_usecase())
