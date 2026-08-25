from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase
from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.message_time_restriction import (
    MESSAGE_TIME_RESTRICTION_KEY,
    MessageTimeRestrictionUseCase,
)
from retail.agents.shared.cache import IntegratedAgentCacheHandler


VALID_RESTRICTION = {
    "is_active": True,
    "periods": {
        "weekdays": {"from": "08:00", "to": "20:00"},
        "saturdays": {"from": "10:00", "to": "12:00"},
    },
}


class MessageTimeRestrictionUseCaseTest(TestCase):
    def setUp(self):
        self.integrated_agent = MagicMock(spec=IntegratedAgent)
        self.integrated_agent.uuid = uuid4()
        self.integrated_agent.config = {}
        self.mock_cache_handler = MagicMock(spec=IntegratedAgentCacheHandler)
        self.use_case = MessageTimeRestrictionUseCase(
            cache_handler=self.mock_cache_handler,
        )

    def test_get_restriction_returns_inactive_when_absent(self):
        result = self.use_case.get_restriction(self.integrated_agent)
        self.assertEqual(result, {"is_active": False, "periods": None})

    def test_get_restriction_returns_inactive_when_config_is_none(self):
        self.integrated_agent.config = None
        result = self.use_case.get_restriction(self.integrated_agent)
        self.assertEqual(result, {"is_active": False, "periods": None})

    def test_get_restriction_returns_stored_block(self):
        self.integrated_agent.config = {MESSAGE_TIME_RESTRICTION_KEY: VALID_RESTRICTION}
        result = self.use_case.get_restriction(self.integrated_agent)
        self.assertEqual(result, VALID_RESTRICTION)

    def test_get_integrated_agent_not_found(self):
        with self.assertRaises(NotFound):
            self.use_case.get_integrated_agent(uuid4())

    def test_upsert_restriction_persists_canonical_shape_and_invalidates_cache(self):
        result = self.use_case.upsert_restriction(
            self.integrated_agent, VALID_RESTRICTION
        )

        self.assertEqual(
            self.integrated_agent.config[MESSAGE_TIME_RESTRICTION_KEY],
            VALID_RESTRICTION,
        )
        self.assertEqual(result, VALID_RESTRICTION)
        self.integrated_agent.save.assert_called_once_with(update_fields=["config"])
        self.mock_cache_handler.invalidate_all_for.assert_called_once_with(
            self.integrated_agent
        )

    def test_upsert_restriction_preserves_sibling_config_keys(self):
        self.integrated_agent.config = {
            "abandoned_cart": {"header_image_type": "no_image"}
        }

        self.use_case.upsert_restriction(self.integrated_agent, VALID_RESTRICTION)

        self.assertEqual(
            self.integrated_agent.config["abandoned_cart"]["header_image_type"],
            "no_image",
        )
        self.assertEqual(
            self.integrated_agent.config[MESSAGE_TIME_RESTRICTION_KEY],
            VALID_RESTRICTION,
        )

    def test_upsert_restriction_replaces_previous_value(self):
        self.integrated_agent.config = {
            MESSAGE_TIME_RESTRICTION_KEY: {
                "is_active": False,
                "periods": {
                    "weekdays": {"from": "09:00", "to": "18:00"},
                    "saturdays": {"from": "09:00", "to": "12:00"},
                },
            }
        }
        updated = {
            "is_active": True,
            "periods": {
                "weekdays": {"from": "07:00", "to": "19:00"},
                "saturdays": {"from": "08:00", "to": "13:00"},
            },
        }

        self.use_case.upsert_restriction(self.integrated_agent, updated)

        self.assertEqual(
            self.integrated_agent.config[MESSAGE_TIME_RESTRICTION_KEY],
            updated,
        )

    def test_upsert_restriction_initializes_config_when_none(self):
        self.integrated_agent.config = None

        self.use_case.upsert_restriction(self.integrated_agent, VALID_RESTRICTION)

        self.assertEqual(
            self.integrated_agent.config[MESSAGE_TIME_RESTRICTION_KEY],
            VALID_RESTRICTION,
        )

    def test_upsert_restriction_persists_inactive_with_periods(self):
        inactive = {
            "is_active": False,
            "periods": VALID_RESTRICTION["periods"],
        }

        result = self.use_case.upsert_restriction(self.integrated_agent, inactive)

        self.assertEqual(
            self.integrated_agent.config[MESSAGE_TIME_RESTRICTION_KEY],
            inactive,
        )
        self.assertEqual(result, inactive)

    def test_delete_restriction_removes_key_and_invalidates_cache(self):
        self.integrated_agent.config = {
            "abandoned_cart": {"header_image_type": "first_item"},
            MESSAGE_TIME_RESTRICTION_KEY: VALID_RESTRICTION,
        }

        self.use_case.delete_restriction(self.integrated_agent)

        self.assertNotIn(MESSAGE_TIME_RESTRICTION_KEY, self.integrated_agent.config)
        self.assertEqual(
            self.integrated_agent.config["abandoned_cart"]["header_image_type"],
            "first_item",
        )
        self.integrated_agent.save.assert_called_once_with(update_fields=["config"])
        self.mock_cache_handler.invalidate_all_for.assert_called_once_with(
            self.integrated_agent
        )

    def test_delete_restriction_is_noop_when_key_absent(self):
        self.use_case.delete_restriction(self.integrated_agent)

        self.integrated_agent.save.assert_not_called()
        self.mock_cache_handler.invalidate_all_for.assert_not_called()

    def test_cache_handler_defaults_to_redis_implementation(self):
        use_case = MessageTimeRestrictionUseCase()
        from retail.agents.shared.cache import IntegratedAgentCacheHandlerRedis

        self.assertIsInstance(use_case.cache_handler, IntegratedAgentCacheHandlerRedis)
