from unittest.mock import patch

from django.test import TestCase, override_settings

from retail.projects.usecases.onboarding_agents.agent_mappings import (
    get_channel_agents,
)
from retail.projects.usecases.onboarding_agents.agents import (
    AbandonedCartAgent,
    OneClickPaymentAgent,
)
from retail.projects.usecases.onboarding_agents.base import PassiveAgent


class TestGetChannelAgents(TestCase):
    def test_raises_for_unsupported_channel(self):
        with self.assertRaises(ValueError) as ctx:
            get_channel_agents("telegram")
        self.assertIn("Unsupported channel", str(ctx.exception))

    @override_settings(
        PASSIVE_AGENTS_WWC={"order_status": "uuid-order"},
    )
    def test_wwc_returns_passive_agents_only(self):
        agents = get_channel_agents("wwc")
        self.assertEqual(len(agents), 1)
        self.assertIsInstance(agents[0], PassiveAgent)
        self.assertEqual(agents[0].uuid, "uuid-order")
        self.assertEqual(agents[0].name, "Order Status")

    @override_settings(
        PASSIVE_AGENTS_WPP_CLOUD={
            "order_status": "uuid-order",
            "one_click_payment": "uuid-ocp",
        },
    )
    def test_wpp_cloud_upgrades_one_click_payment(self):
        agents = get_channel_agents("wpp-cloud")

        passive = next(a for a in agents if a.uuid == "uuid-order")
        upgraded = next(a for a in agents if a.uuid == "uuid-ocp")

        self.assertIsInstance(passive, PassiveAgent)
        self.assertIsInstance(upgraded, OneClickPaymentAgent)
        self.assertEqual(upgraded.name, "One Click Payment")

    @override_settings(PASSIVE_AGENTS_WPP_CLOUD={})
    def test_wpp_cloud_includes_legacy_active_agents(self):
        agents = get_channel_agents("wpp-cloud")
        self.assertTrue(any(isinstance(a, AbandonedCartAgent) for a in agents))

    @override_settings(
        PASSIVE_AGENTS_WPP_CLOUD={
            "order_status": "uuid-order",
            "one_click_payment": "",
        },
    )
    def test_skips_entries_with_empty_uuid(self):
        agents = get_channel_agents("wpp-cloud")
        codes = [
            a.uuid
            for a in agents
            if isinstance(a, (PassiveAgent, OneClickPaymentAgent))
        ]
        self.assertIn("uuid-order", codes)
        self.assertNotIn("", codes)

    @override_settings(
        PASSIVE_AGENTS_WPP_CLOUD={"order_status": "uuid-order"},
    )
    def test_warns_when_registered_behavior_missing_from_env(self):
        with patch(
            "retail.projects.usecases.onboarding_agents.agent_mappings.logger"
        ) as mock_logger:
            get_channel_agents("wpp-cloud")

        warning_calls = [c for c in mock_logger.warning.call_args_list]
        self.assertTrue(
            any("one_click_payment" in str(c) for c in warning_calls),
            "Expected a warning about missing 'one_click_payment' code.",
        )
