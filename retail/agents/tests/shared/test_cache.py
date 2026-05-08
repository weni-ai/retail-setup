import uuid

from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.shared.cache import (
    AgentRole,
    IntegratedAgentCacheHandlerRedis,
)


PAYMENT_RECOVERY_AGENT_UUID = str(uuid.uuid4())
ABANDONED_CART_AGENT_UUID = str(uuid.uuid4())
ORDER_STATUS_AGENT_UUID = str(uuid.uuid4())


class IntegratedAgentCacheHandlerRedisWebhookTest(TestCase):
    """Tests for the webhook cache layer (one entry per IntegratedAgent.uuid)."""

    def setUp(self):
        self.cache_handler = IntegratedAgentCacheHandlerRedis()
        self.test_uuid = uuid.uuid4()
        self.integrated_agent = Mock(spec=IntegratedAgent)
        self.integrated_agent.uuid = self.test_uuid

    def test_init_with_default_values(self):
        handler = IntegratedAgentCacheHandlerRedis()
        self.assertEqual(handler.cache_key_prefix, "integrated_agent_webhook")
        self.assertEqual(handler.cache_time, 30)

    def test_init_with_custom_values(self):
        handler = IntegratedAgentCacheHandlerRedis(
            cache_key_prefix="custom_prefix", cache_time=60
        )
        self.assertEqual(handler.cache_key_prefix, "custom_prefix")
        self.assertEqual(handler.cache_time, 60)

    def test_get_cache_key(self):
        expected_key = f"integrated_agent_webhook_{self.test_uuid}"
        cache_key = self.cache_handler.get_cache_key(self.test_uuid)
        self.assertEqual(cache_key, expected_key)

    def test_get_cache_key_with_custom_prefix(self):
        handler = IntegratedAgentCacheHandlerRedis(cache_key_prefix="custom")
        expected_key = f"custom_{self.test_uuid}"
        cache_key = handler.get_cache_key(self.test_uuid)
        self.assertEqual(cache_key, expected_key)

    @patch("django.core.cache.cache.set")
    def test_set_cached_agent(self, mock_cache_set):
        self.cache_handler.set_cached_agent(self.integrated_agent)
        expected_key = f"integrated_agent_webhook_{self.test_uuid}"
        mock_cache_set.assert_called_once_with(
            expected_key, self.integrated_agent, timeout=30
        )

    @patch("django.core.cache.cache.get")
    def test_get_cached_agent_exists(self, mock_cache_get):
        mock_cache_get.return_value = self.integrated_agent
        cached_agent = self.cache_handler.get_cached_agent(self.test_uuid)
        expected_key = f"integrated_agent_webhook_{self.test_uuid}"
        mock_cache_get.assert_called_once_with(expected_key)
        self.assertEqual(cached_agent, self.integrated_agent)

    @patch("django.core.cache.cache.get")
    def test_get_cached_agent_not_exists(self, mock_cache_get):
        mock_cache_get.return_value = None
        cached_agent = self.cache_handler.get_cached_agent(self.test_uuid)
        expected_key = f"integrated_agent_webhook_{self.test_uuid}"
        mock_cache_get.assert_called_once_with(expected_key)
        self.assertIsNone(cached_agent)

    @patch("django.core.cache.cache.delete")
    def test_clear_cached_agent(self, mock_cache_delete):
        self.cache_handler.clear_cached_agent(self.test_uuid)
        expected_key = f"integrated_agent_webhook_{self.test_uuid}"
        mock_cache_delete.assert_called_once_with(expected_key)

    @patch("django.core.cache.cache.set")
    def test_set_cached_agent_with_timeout(self, mock_cache_set):
        custom_handler = IntegratedAgentCacheHandlerRedis(cache_time=60)
        custom_handler.set_cached_agent(self.integrated_agent)
        expected_key = f"integrated_agent_webhook_{self.test_uuid}"
        mock_cache_set.assert_called_once_with(
            expected_key, self.integrated_agent, timeout=60
        )


class IntegratedAgentCacheHandlerRedisRoleCacheTest(TestCase):
    """Tests for the role cache layer (one entry per (role, project))."""

    def setUp(self):
        self.cache_handler = IntegratedAgentCacheHandlerRedis()
        self.project_uuid = uuid.uuid4()
        self.integrated_agent = Mock(spec=IntegratedAgent)
        self.integrated_agent.uuid = uuid.uuid4()
        self.integrated_agent.project = Mock()
        self.integrated_agent.project.uuid = self.project_uuid

    def test_get_role_cache_key(self):
        key = self.cache_handler.get_role_cache_key(
            self.project_uuid, AgentRole.PAYMENT_RECOVERY
        )
        self.assertEqual(key, f"payment_recovery_agent_{self.project_uuid}")

    def test_get_role_cache_key_for_each_role(self):
        for role, expected_prefix in (
            (AgentRole.PAYMENT_RECOVERY, "payment_recovery"),
            (AgentRole.ABANDONED_CART, "abandoned_cart"),
            (AgentRole.ORDER_STATUS, "order_status"),
        ):
            with self.subTest(role=role):
                key = self.cache_handler.get_role_cache_key(self.project_uuid, role)
                self.assertEqual(key, f"{expected_prefix}_agent_{self.project_uuid}")

    @patch("django.core.cache.cache.get")
    def test_get_role_agent_returns_cached_value(self, mock_cache_get):
        mock_cache_get.return_value = self.integrated_agent
        result = self.cache_handler.get_role_agent(
            self.project_uuid, AgentRole.PAYMENT_RECOVERY
        )
        mock_cache_get.assert_called_once_with(
            f"payment_recovery_agent_{self.project_uuid}"
        )
        self.assertEqual(result, self.integrated_agent)

    @patch("django.core.cache.cache.set")
    def test_set_role_agent_uses_role_ttl(self, mock_cache_set):
        self.cache_handler.set_role_agent(self.integrated_agent, AgentRole.ORDER_STATUS)
        mock_cache_set.assert_called_once_with(
            f"order_status_agent_{self.project_uuid}",
            self.integrated_agent,
            timeout=21600,
        )

    @patch("django.core.cache.cache.delete")
    def test_clear_role_agent(self, mock_cache_delete):
        self.cache_handler.clear_role_agent(self.project_uuid, AgentRole.ABANDONED_CART)
        mock_cache_delete.assert_called_once_with(
            f"abandoned_cart_agent_{self.project_uuid}"
        )

    @patch("django.core.cache.cache.delete")
    def test_clear_agent_active_flag(self, mock_cache_delete):
        self.cache_handler.clear_agent_active_flag(
            "myaccount", AgentRole.PAYMENT_RECOVERY
        )
        mock_cache_delete.assert_called_once_with(
            "agent_active_myaccount_payment_recovery"
        )


class ResolveRoleTest(TestCase):
    """Tests for ``IntegratedAgentCacheHandler.resolve_role``."""

    def setUp(self):
        self.cache_handler = IntegratedAgentCacheHandlerRedis()
        self.integrated_agent = Mock(spec=IntegratedAgent)
        self.integrated_agent.uuid = uuid.uuid4()
        self.integrated_agent.agent = Mock()
        self.integrated_agent.agent.uuid = uuid.uuid4()
        self.integrated_agent.project = Mock()
        self.integrated_agent.project.uuid = uuid.uuid4()
        self.integrated_agent.project.vtex_account = "myaccount"

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_AGENT_UUID)
    def test_resolves_payment_recovery_role(self):
        self.integrated_agent.agent.uuid = PAYMENT_RECOVERY_AGENT_UUID
        role = self.cache_handler.resolve_role(self.integrated_agent)
        self.assertEqual(role, AgentRole.PAYMENT_RECOVERY)

    @override_settings(ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID)
    def test_resolves_abandoned_cart_role(self):
        self.integrated_agent.agent.uuid = ABANDONED_CART_AGENT_UUID
        role = self.cache_handler.resolve_role(self.integrated_agent)
        self.assertEqual(role, AgentRole.ABANDONED_CART)

    @override_settings(ORDER_STATUS_AGENT_UUID=ORDER_STATUS_AGENT_UUID)
    def test_resolves_order_status_role(self):
        self.integrated_agent.agent.uuid = ORDER_STATUS_AGENT_UUID
        role = self.cache_handler.resolve_role(self.integrated_agent)
        self.assertEqual(role, AgentRole.ORDER_STATUS)

    @override_settings(
        PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_AGENT_UUID,
        ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID,
        ORDER_STATUS_AGENT_UUID=ORDER_STATUS_AGENT_UUID,
    )
    def test_returns_none_for_unrelated_agent(self):
        self.integrated_agent.agent.uuid = str(uuid.uuid4())
        role = self.cache_handler.resolve_role(self.integrated_agent)
        self.assertIsNone(role)

    @override_settings(
        PAYMENT_RECOVERY_AGENT_UUID="",
        ABANDONED_CART_AGENT_UUID="",
        ORDER_STATUS_AGENT_UUID="",
    )
    def test_returns_none_when_settings_are_empty(self):
        self.integrated_agent.agent.uuid = PAYMENT_RECOVERY_AGENT_UUID
        role = self.cache_handler.resolve_role(self.integrated_agent)
        self.assertIsNone(role)


class InvalidateAllForTest(TestCase):
    """Tests for ``IntegratedAgentCacheHandler.invalidate_all_for``."""

    def setUp(self):
        self.cache_handler = IntegratedAgentCacheHandlerRedis()
        self.integrated_agent = Mock(spec=IntegratedAgent)
        self.integrated_agent.uuid = uuid.uuid4()
        self.integrated_agent.agent = Mock()
        self.integrated_agent.agent.uuid = PAYMENT_RECOVERY_AGENT_UUID
        self.integrated_agent.project = Mock()
        self.integrated_agent.project.uuid = uuid.uuid4()
        self.integrated_agent.project.vtex_account = "myaccount"

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_AGENT_UUID)
    @patch("django.core.cache.cache.delete")
    def test_clears_all_keys_for_known_role(self, mock_cache_delete):
        self.cache_handler.invalidate_all_for(self.integrated_agent)

        cleared_keys = [call.args[0] for call in mock_cache_delete.call_args_list]
        self.assertIn(
            f"integrated_agent_webhook_{self.integrated_agent.uuid}", cleared_keys
        )
        self.assertIn(
            f"payment_recovery_agent_{self.integrated_agent.project.uuid}",
            cleared_keys,
        )
        self.assertIn("agent_active_myaccount_payment_recovery", cleared_keys)

    @override_settings(
        PAYMENT_RECOVERY_AGENT_UUID="",
        ABANDONED_CART_AGENT_UUID="",
        ORDER_STATUS_AGENT_UUID="",
    )
    @patch("django.core.cache.cache.delete")
    def test_clears_only_webhook_key_when_role_unknown(self, mock_cache_delete):
        self.cache_handler.invalidate_all_for(self.integrated_agent)

        cleared_keys = [call.args[0] for call in mock_cache_delete.call_args_list]
        self.assertEqual(
            cleared_keys,
            [f"integrated_agent_webhook_{self.integrated_agent.uuid}"],
        )

    @override_settings(PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_AGENT_UUID)
    @patch("django.core.cache.cache.delete")
    def test_skips_agent_active_flag_when_vtex_account_missing(self, mock_cache_delete):
        self.integrated_agent.project.vtex_account = ""

        self.cache_handler.invalidate_all_for(self.integrated_agent)

        cleared_keys = [call.args[0] for call in mock_cache_delete.call_args_list]
        self.assertNotIn("agent_active__payment_recovery", cleared_keys)
        self.assertIn(
            f"payment_recovery_agent_{self.integrated_agent.project.uuid}",
            cleared_keys,
        )


class ClearCachedAgentsTest(TestCase):
    """Tests for the batch ``clear_cached_agents`` helper."""

    def setUp(self):
        self.cache_handler = IntegratedAgentCacheHandlerRedis()

    @patch("django.core.cache.cache.delete_many")
    def test_clear_cached_agents_uses_delete_many(self, mock_delete_many):
        uuids = [uuid.uuid4(), uuid.uuid4()]

        self.cache_handler.clear_cached_agents(uuids)

        expected_keys = [f"integrated_agent_webhook_{u}" for u in uuids]
        mock_delete_many.assert_called_once_with(expected_keys)

    @patch("django.core.cache.cache.delete_many")
    def test_clear_cached_agents_no_op_when_empty(self, mock_delete_many):
        self.cache_handler.clear_cached_agents([])

        mock_delete_many.assert_not_called()
