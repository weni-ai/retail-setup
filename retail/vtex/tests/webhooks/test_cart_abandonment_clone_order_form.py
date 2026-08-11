import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.vtex.usecases.clone_order_form import ClonedOrderFormDTO
from retail.webhooks.vtex.services_cart_abandonment_unified import (
    CartAbandonmentService,
    _build_cart_sentry_tags,
    _build_log_context,
)


def _build_order_form(items=None, email="buyer@example.com"):
    return {
        "orderFormId": "order-form-1",
        "items": (
            items
            if items is not None
            else [{"id": "sku-1", "quantity": 1, "price": 1000, "seller": "1"}]
        ),
        "clientProfileData": {"email": email},
        "clientPreferencesData": {"locale": "pt-BR"},
        "storePreferencesData": {"currencyCode": "BRL"},
        "marketingData": {"utmCampaign": "summer", "coupon": "SAVE10"},
        "shippingData": {"selectedAddresses": []},
        "salesChannel": "1",
    }


@override_settings(ABANDONED_CART_CLONE_ORDER_FORM_ENABLED=True)
class CartAbandonmentCloneOrderFormTests(TestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="test-account"
        )
        self.agent = Agent.objects.create(
            name="Abandoned cart",
            slug="abandoned-cart",
            description="x",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            config={"abandoned_cart": {}},
        )
        self.cart = Cart.objects.create(
            order_form_id="order-form-1",
            phone_number="5511999999999",
            project=self.project,
            integrated_agent=self.integrated_agent,
            config={
                "client_profile": {"email": "buyer@example.com"},
                "cart_items": [
                    {"id": "sku-1", "quantity": 1, "price": 1000, "seller": "1"}
                ],
                "locale": "pt-BR",
                "client_name": "Ada",
            },
        )
        self.mock_clone = MagicMock()
        self.service = CartAbandonmentService(clone_order_form_use_case=self.mock_clone)
        self.service.notification_lock_service = MagicMock()
        self.service.notification_lock_service.acquire_lock.return_value = True

    def test_clone_runs_after_gates_and_swaps_payload_order_form_id(self):
        cloned = ClonedOrderFormDTO(
            order_form_id="clone-of",
            marketing_data={"utmCampaign": "summer", "coupon": "SAVE10"},
        )
        self.mock_clone.execute.return_value = cloned

        with patch(
            "retail.vtex.tasks.task_agent_webhook", return_value={"ok": True}
        ) as mock_webhook:
            self.service._mark_cart_as_abandoned(
                cart=self.cart,
                order_form=_build_order_form(),
                client_profile={"email": "buyer@example.com"},
                integration_config=self.integrated_agent,
            )

        self.mock_clone.execute.assert_called_once()
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.notification_order_form_id, "clone-of")
        self.assertEqual(self.cart.status, "delivered_success")

        payload = mock_webhook.call_args.kwargs["payload"]
        self.assertEqual(payload["order_form_id"], "clone-of")
        self.assertEqual(
            payload["marketing_data"],
            {"utmCampaign": "summer", "coupon": "SAVE10"},
        )

    def test_clone_failure_falls_back_to_original_order_form_id(self):
        self.mock_clone.execute.return_value = None

        with patch(
            "retail.vtex.tasks.task_agent_webhook", return_value={"ok": True}
        ) as mock_webhook:
            with patch(
                "retail.webhooks.vtex.services_cart_abandonment_unified.sentry_error_scope"
            ):
                self.service._mark_cart_as_abandoned(
                    cart=self.cart,
                    order_form=_build_order_form(),
                    client_profile={"email": "buyer@example.com"},
                    integration_config=self.integrated_agent,
                )

        self.cart.refresh_from_db()
        self.assertIsNone(self.cart.notification_order_form_id)
        self.assertEqual(self.cart.status, "delivered_success")

        payload = mock_webhook.call_args.kwargs["payload"]
        self.assertEqual(payload["order_form_id"], "order-form-1")
        self.assertNotIn("marketing_data", payload)

    def test_clone_exception_falls_back_to_original_order_form_id(self):
        self.mock_clone.execute.side_effect = RuntimeError("vtex down")

        with patch(
            "retail.vtex.tasks.task_agent_webhook", return_value={"ok": True}
        ) as mock_webhook:
            with patch(
                "retail.webhooks.vtex.services_cart_abandonment_unified.sentry_error_scope"
            ):
                self.service._mark_cart_as_abandoned(
                    cart=self.cart,
                    order_form=_build_order_form(),
                    client_profile={"email": "buyer@example.com"},
                    integration_config=self.integrated_agent,
                )

        self.cart.refresh_from_db()
        self.assertIsNone(self.cart.notification_order_form_id)
        payload = mock_webhook.call_args.kwargs["payload"]
        self.assertEqual(payload["order_form_id"], "order-form-1")

    def test_injects_cart_order_form_id_when_source_omits_it(self):
        self.mock_clone.execute.return_value = ClonedOrderFormDTO(
            order_form_id="clone-of",
            marketing_data=None,
        )
        order_form = _build_order_form()
        del order_form["orderFormId"]

        with patch("retail.vtex.tasks.task_agent_webhook", return_value={"ok": True}):
            self.service._mark_cart_as_abandoned(
                cart=self.cart,
                order_form=order_form,
                client_profile={"email": "buyer@example.com"},
                integration_config=self.integrated_agent,
            )

        source = self.mock_clone.execute.call_args.kwargs["order_form"]
        self.assertEqual(source["orderFormId"], "order-form-1")

    def test_clone_not_called_when_gate_skips(self):
        self.service.notification_lock_service.acquire_lock.return_value = False

        self.service._mark_cart_as_abandoned(
            cart=self.cart,
            order_form=_build_order_form(),
            client_profile={"email": "buyer@example.com"},
            integration_config=self.integrated_agent,
        )

        self.mock_clone.execute.assert_not_called()
        self.cart.refresh_from_db()
        self.assertIsNone(self.cart.notification_order_form_id)

    @override_settings(ABANDONED_CART_CLONE_ORDER_FORM_ENABLED=False)
    def test_feature_flag_off_skips_clone(self):
        with patch(
            "retail.vtex.tasks.task_agent_webhook", return_value={"ok": True}
        ) as mock_webhook:
            self.service._mark_cart_as_abandoned(
                cart=self.cart,
                order_form=_build_order_form(),
                client_profile={"email": "buyer@example.com"},
                integration_config=self.integrated_agent,
            )

        self.mock_clone.execute.assert_not_called()
        payload = mock_webhook.call_args.kwargs["payload"]
        self.assertEqual(payload["order_form_id"], "order-form-1")
        self.assertNotIn("marketing_data", payload)


@override_settings(ABANDONED_CART_CLONE_ORDER_FORM_ENABLED=True)
class CartAbandonmentCloneDoesNotAffectLegacyFlowTests(TestCase):
    """Legacy IntegratedFeature flow must not mint clones."""

    def setUp(self):
        super().setUp()
        self.feature = Feature.objects.create(
            can_vtex_integrate=True, code="abandoned_cart"
        )
        self.user = User.objects.create()
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="test-account"
        )
        self.integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature,
            project=self.project,
            user=self.user,
            config={},
        )
        self.cart = Cart.objects.create(
            order_form_id="order-form-1",
            phone_number="5511999999999",
            project=self.project,
            integrated_feature=self.integrated_feature,
            config={
                "client_profile": {"email": "buyer@example.com"},
                "cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}],
                "locale": "pt-BR",
            },
        )
        self.mock_clone = MagicMock()
        self.service = CartAbandonmentService(clone_order_form_use_case=self.mock_clone)
        self.service.notification_lock_service = MagicMock()
        self.service.notification_lock_service.acquire_lock.return_value = True

    def test_legacy_flow_does_not_clone(self):
        with patch.object(
            self.service, "_execute_legacy_flow", return_value=True
        ) as mock_legacy:
            self.service._mark_cart_as_abandoned(
                cart=self.cart,
                order_form=_build_order_form(),
                client_profile={"email": "buyer@example.com"},
                integration_config=self.integrated_feature,
            )

        self.mock_clone.execute.assert_not_called()
        self.cart.refresh_from_db()
        self.assertIsNone(self.cart.notification_order_form_id)
        mock_legacy.assert_called_once()
        cart_data = mock_legacy.call_args.args[2]
        self.assertEqual(cart_data.order_form_id, "order-form-1")
        self.assertIsNone(cart_data.notification_order_form_id)


class CartNotificationOrderFormLogContextTests(TestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="test-account"
        )
        self.cart = Cart.objects.create(
            order_form_id="order-form-1",
            notification_order_form_id="clone-of",
            phone_number="5511999999999",
            project=self.project,
            config={},
        )

    def test_log_context_includes_notification_order_form(self):
        context = _build_log_context(self.cart)
        self.assertIn("notification_order_form=clone-of", context)

    def test_sentry_tags_include_notification_order_form(self):
        tags = _build_cart_sentry_tags(self.cart)
        self.assertEqual(tags["notification_order_form_id"], "clone-of")
