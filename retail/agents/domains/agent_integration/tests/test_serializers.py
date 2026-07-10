"""Serializer contract tests for the agent_integration domain.

These serializers drive the public integrated-agent API (CRUD, query
params, read projection) and the pluggable feature configs
(``abandoned_cart``, ``delivered_order_tracking``). They wire
validation and partial updates in non-obvious ways: ``to_internal_value``
is overridden to drop unsent fields so frontends can PATCH a single
setting without having to resend every other one. These tests pin:

- Field-level validation (required, min/max, choices, null handling).
- Partial-update semantics: only explicitly-sent fields land in
  ``validated_data``; absent fields stay untouched.
- Nested validation error propagation on ``UpdateIntegratedAgentSerializer``.
- The ``ReadIntegratedAgentSerializer`` projection: webhook URL
  construction, config-driven feature flags, defaults when a block is
  missing, and the delegation to ``PushAgentUseCase`` for the
  "has delivered order templates" toggle.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from retail.agents.domains.agent_integration.serializers import (
    AbandonedCartConfigSerializer,
    DeliveredOrderTrackingEnableSerializer,
    ReadIntegratedAgentSerializer,
    RetrieveIntegratedAgentQueryParamsSerializer,
    TemplateLanguageSerializer,
    UpdateIntegratedAgentSerializer,
)


class DeliveredOrderTrackingEnableSerializerTests(SimpleTestCase):
    def test_valid_payload_is_accepted(self):
        serializer = DeliveredOrderTrackingEnableSerializer(
            data={"vtex_app_key": "key-123", "vtex_app_token": "token-456"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data,
            {"vtex_app_key": "key-123", "vtex_app_token": "token-456"},
        )

    def test_vtex_app_key_is_required(self):
        serializer = DeliveredOrderTrackingEnableSerializer(
            data={"vtex_app_token": "token-456"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("vtex_app_key", serializer.errors)

    def test_vtex_app_token_is_required(self):
        serializer = DeliveredOrderTrackingEnableSerializer(
            data={"vtex_app_key": "key-123"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("vtex_app_token", serializer.errors)

    def test_vtex_app_key_rejects_over_max_length(self):
        serializer = DeliveredOrderTrackingEnableSerializer(
            data={"vtex_app_key": "x" * 101, "vtex_app_token": "y"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("vtex_app_key", serializer.errors)

    def test_vtex_app_token_rejects_over_max_length(self):
        serializer = DeliveredOrderTrackingEnableSerializer(
            data={"vtex_app_key": "x", "vtex_app_token": "y" * 201}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("vtex_app_token", serializer.errors)


class RetrieveIntegratedAgentQueryParamsSerializerTests(SimpleTestCase):
    def test_defaults_when_no_params(self):
        serializer = RetrieveIntegratedAgentQueryParamsSerializer(data={})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data,
            {"show_all": False, "start": None, "end": None},
        )

    def test_show_all_accepts_truthy_values(self):
        serializer = RetrieveIntegratedAgentQueryParamsSerializer(
            data={"show_all": "true"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertTrue(serializer.validated_data["show_all"])

    def test_valid_dates_are_parsed(self):
        serializer = RetrieveIntegratedAgentQueryParamsSerializer(
            data={"start": "2026-01-01", "end": "2026-01-31"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(str(serializer.validated_data["start"]), "2026-01-01")
        self.assertEqual(str(serializer.validated_data["end"]), "2026-01-31")

    def test_invalid_date_rejected(self):
        serializer = RetrieveIntegratedAgentQueryParamsSerializer(
            data={"start": "not-a-date"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("start", serializer.errors)


class AbandonedCartConfigSerializerPartialUpdateTests(SimpleTestCase):
    def test_empty_payload_produces_empty_validated_data(self):
        serializer = AbandonedCartConfigSerializer(data={})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, {})

    def test_only_sent_fields_land_in_validated_data(self):
        serializer = AbandonedCartConfigSerializer(
            data={"abandonment_time_minutes": 90}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        # Other fields — header_image_type, minimum_cart_value,
        # notification_cooldown_hours — must NOT appear so the caller
        # can patch a single setting without resetting defaults.
        self.assertEqual(
            serializer.validated_data,
            {"abandonment_time_minutes": 90},
        )

    def test_full_payload_round_trips(self):
        data = {
            "header_image_type": "most_expensive",
            "abandonment_time_minutes": 30,
            "minimum_cart_value": 12.5,
            "notification_cooldown_hours": 24,
        }
        serializer = AbandonedCartConfigSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, data)

    def test_null_minimum_cart_value_is_accepted(self):
        serializer = AbandonedCartConfigSerializer(data={"minimum_cart_value": None})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data["minimum_cart_value"])

    def test_null_notification_cooldown_is_accepted(self):
        serializer = AbandonedCartConfigSerializer(
            data={"notification_cooldown_hours": None}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data["notification_cooldown_hours"])


class AbandonedCartConfigSerializerValidationTests(SimpleTestCase):
    def test_invalid_header_image_type(self):
        serializer = AbandonedCartConfigSerializer(
            data={"header_image_type": "not-a-choice"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("header_image_type", serializer.errors)

    def test_abandonment_time_must_be_positive(self):
        serializer = AbandonedCartConfigSerializer(data={"abandonment_time_minutes": 0})
        self.assertFalse(serializer.is_valid())
        self.assertIn("abandonment_time_minutes", serializer.errors)

    def test_minimum_cart_value_rejects_negative(self):
        serializer = AbandonedCartConfigSerializer(data={"minimum_cart_value": -1.0})
        self.assertFalse(serializer.is_valid())
        self.assertIn("minimum_cart_value", serializer.errors)

    def test_notification_cooldown_rejects_over_seven_days(self):
        serializer = AbandonedCartConfigSerializer(
            data={"notification_cooldown_hours": 169}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("notification_cooldown_hours", serializer.errors)

    def test_notification_cooldown_rejects_under_one_hour(self):
        serializer = AbandonedCartConfigSerializer(
            data={"notification_cooldown_hours": 0}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("notification_cooldown_hours", serializer.errors)


class UpdateIntegratedAgentSerializerTests(SimpleTestCase):
    def test_empty_payload_is_valid_with_no_validated_fields(self):
        serializer = UpdateIntegratedAgentSerializer(data={})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, {})

    def test_partial_update_keeps_only_sent_fields(self):
        serializer = UpdateIntegratedAgentSerializer(data={"contact_percentage": 25})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, {"contact_percentage": 25})

    def test_global_rule_accepts_null(self):
        serializer = UpdateIntegratedAgentSerializer(data={"global_rule": None})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data["global_rule"])

    def test_nested_abandoned_cart_config_is_validated(self):
        serializer = UpdateIntegratedAgentSerializer(
            data={"abandoned_cart_config": {"header_image_type": "no_image"}}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["abandoned_cart_config"],
            {"header_image_type": "no_image"},
        )

    def test_nested_abandoned_cart_config_rejects_invalid_value(self):
        serializer = UpdateIntegratedAgentSerializer(
            data={"abandoned_cart_config": {"header_image_type": "bogus"}}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("abandoned_cart_config", serializer.errors)


def _integrated_agent(**overrides):
    """Duck-typed integrated-agent stub used by the read serializer."""
    defaults = dict(
        uuid=uuid4(),
        channel_uuid=uuid4(),
        contact_percentage=10,
        global_rule_prompt="rule",
        agent=SimpleNamespace(description="desc for agent", uuid=uuid4()),
        config={},
        templates=MagicMock(),
    )
    defaults["templates"].all.return_value = []
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@override_settings(DOMAIN="https://retail.example.com")
class ReadIntegratedAgentSerializerTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        # ReadTemplateSerializer would try to build an S3Service; since
        # we always seed with an empty templates queryset, patching the
        # whole class keeps the test hermetic (no AWS config required).
        patcher = patch(
            "retail.agents.domains.agent_integration.serializers."
            "ReadTemplateSerializer"
        )
        self.mock_read_template = patcher.start()
        self.mock_read_template.return_value.data = []
        self.addCleanup(patcher.stop)

        push_patcher = patch(
            "retail.agents.domains.agent_integration.serializers."
            "PushAgentUseCase.has_delivered_order_templates_by_integrated_agent",
            return_value=False,
        )
        self.mock_has_delivered = push_patcher.start()
        self.addCleanup(push_patcher.stop)

    def test_webhook_url_is_built_from_domain_setting(self):
        obj = _integrated_agent()
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertEqual(
            data["webhook_url"],
            f"https://retail.example.com/api/v3/agents/webhook/{obj.uuid}/",
        )

    @override_settings(ABANDONED_CART_AGENT_UUID="abandoned-cart-agent-uuid")
    def test_webhook_url_uses_abandoned_cart_endpoint_for_abandoned_cart_agent(self):
        obj = _integrated_agent(
            agent=SimpleNamespace(
                description="desc for agent",
                uuid="abandoned-cart-agent-uuid",
            )
        )
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertEqual(
            data["webhook_url"],
            f"https://retail.example.com/api/v3/agents/abandoned-cart-webhook/{obj.uuid}/",
        )

    def test_description_is_sourced_from_agent(self):
        obj = _integrated_agent(
            agent=SimpleNamespace(description="hello", uuid=uuid4())
        )
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertEqual(data["description"], "hello")

    def test_templates_delegates_to_read_template_serializer(self):
        obj = _integrated_agent()
        ReadIntegratedAgentSerializer(obj).data
        self.mock_read_template.assert_called_once()
        # many=True is required so a queryset of templates serialises
        # as a list rather than a single object.
        _args, kwargs = self.mock_read_template.call_args
        self.assertTrue(kwargs.get("many"))

    def test_initial_template_language_comes_from_config(self):
        obj = _integrated_agent(config={"initial_template_language": "pt_BR"})
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertEqual(data["initial_template_language"], "pt_BR")

    def test_initial_template_language_defaults_to_none_when_absent(self):
        obj = _integrated_agent(config={})
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertIsNone(data["initial_template_language"])

    def test_delivered_order_tracking_defaults_when_config_missing(self):
        obj = _integrated_agent(config={})
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertEqual(
            data["delivered_order_tracking_config"],
            {"is_enabled": False, "vtex_app_key": "", "webhook_url": ""},
        )

    def test_delivered_order_tracking_projects_stored_config(self):
        obj = _integrated_agent(
            config={
                "delivered_order_tracking": {
                    "is_enabled": True,
                    "vtex_app_key": "k",
                    "webhook_url": "https://hook",
                }
            }
        )
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertEqual(
            data["delivered_order_tracking_config"],
            {
                "is_enabled": True,
                "vtex_app_key": "k",
                "webhook_url": "https://hook",
            },
        )

    def test_has_delivered_order_templates_delegates_to_push_usecase(self):
        self.mock_has_delivered.return_value = True
        obj = _integrated_agent()
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertTrue(data["has_delivered_order_templates"])
        self.mock_has_delivered.assert_called_once_with(str(obj.uuid))

    def test_abandoned_cart_config_returns_none_when_block_absent(self):
        obj = _integrated_agent(config={})
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertIsNone(data["abandoned_cart_config"])

    def test_abandoned_cart_config_uses_defaults_for_missing_fields(self):
        obj = _integrated_agent(
            # An empty dict literally cannot signal "config exists but
            # empty" because the serializer treats ``{}`` as falsy —
            # we need at least one field present to get the defaults
            # shape back, which mirrors the real-world write path
            # (config is only set when the feature is configured).
            config={"abandoned_cart": {"header_image_type": "no_image"}}
        )
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertEqual(
            data["abandoned_cart_config"],
            {
                "header_image_type": "no_image",
                "abandonment_time_minutes": 60,
                "minimum_cart_value": None,
                "notification_cooldown_hours": None,
            },
        )

    def test_abandoned_cart_config_projects_full_block(self):
        obj = _integrated_agent(
            config={
                "abandoned_cart": {
                    "header_image_type": "first_item",
                    "abandonment_time_minutes": 45,
                    "minimum_cart_value": 20.0,
                    "notification_cooldown_hours": 12,
                }
            }
        )
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertEqual(
            data["abandoned_cart_config"],
            {
                "header_image_type": "first_item",
                "abandonment_time_minutes": 45,
                "minimum_cart_value": 20.0,
                "notification_cooldown_hours": 12,
            },
        )

    def test_payment_recovery_config_includes_sales_channels(self):
        obj = _integrated_agent(
            config={
                "payment_recovery": {
                    "hook_created": True,
                    "delay_minutes": 5,
                    "sales_channels": ["2", "3"],
                }
            }
        )
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertEqual(data["payment_recovery_config"]["sales_channels"], ["2", "3"])

    def test_payment_recovery_config_defaults_sales_channels_when_absent(self):
        obj = _integrated_agent(
            config={"payment_recovery": {"hook_created": True, "delay_minutes": 5}}
        )
        data = ReadIntegratedAgentSerializer(obj).data
        self.assertEqual(data["payment_recovery_config"]["sales_channels"], ["1"])


class TemplateLanguageSerializerTests(SimpleTestCase):
    def test_valid_payload_round_trips(self):
        serializer = TemplateLanguageSerializer(
            data={"code": "pt_BR", "display_name": "Portuguese (Brazil)"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data,
            {"code": "pt_BR", "display_name": "Portuguese (Brazil)"},
        )

    def test_code_is_required(self):
        serializer = TemplateLanguageSerializer(data={"display_name": "English"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("code", serializer.errors)

    def test_display_name_is_required(self):
        serializer = TemplateLanguageSerializer(data={"code": "en"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("display_name", serializer.errors)
