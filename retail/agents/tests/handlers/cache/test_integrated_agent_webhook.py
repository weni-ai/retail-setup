import uuid
from unittest.mock import Mock, patch

from django.test import TestCase

from retail.agents.models import IntegratedAgent
from retail.agents.handlers.cache.integrated_agent_webhook import (
    IntegratedAgentCacheHandlerRedis,
)


class IntegratedAgentCacheHandlerRedisTest(TestCase):
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

    @patch("django.core.cache.cache.delete")
    def test_clear_cached_agent_not_exists(self, mock_cache_delete):
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
