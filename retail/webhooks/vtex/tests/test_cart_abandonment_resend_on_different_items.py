import uuid
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.test import TestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.webhooks.vtex.services_cart_abandonment_unified import (
    ALLOW_RESEND_ON_DIFFERENT_CART_ITEMS_KEY,
    CartAbandonmentService,
)


class AllowResendOnDifferentCartItemsTests(TestCase):
    """Tests for the per-client allow_resend_on_different_cart_items flag."""

    def setUp(self):
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
            config={ALLOW_RESEND_ON_DIFFERENT_CART_ITEMS_KEY: True},
        )
        self.agent = Agent.objects.create(
            name="Abandoned Cart Agent",
            slug="abandoned-cart-resend",
            description="test",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            config={
                "abandoned_cart": {
                    ALLOW_RESEND_ON_DIFFERENT_CART_ITEMS_KEY: True,
                }
            },
        )
        self.service = CartAbandonmentService()

    def _make_cart(self, integration_config, **overrides) -> Cart:
        defaults = {
            "order_form_id": "of-1",
            "phone_number": "5511999999999",
            "project": self.project,
            "config": {"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        }
        if isinstance(integration_config, IntegratedFeature):
            defaults["integrated_feature"] = integration_config
        else:
            defaults["integrated_agent"] = integration_config
        defaults.update(overrides)
        return Cart.objects.create(**defaults)

    def test_order_form_dedup_allows_resend_when_skus_differ(self):
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": [{"id": "sku-2", "quantity": 1, "price": 2000}]},
        )

        self.assertFalse(
            self.service._check_order_form_already_notified(
                new_cart, self.integrated_feature
            )
        )

    def test_order_form_dedup_allows_resend_when_quantities_differ(self):
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": [{"id": "sku-1", "quantity": 2, "price": 1000}]},
        )

        self.assertFalse(
            self.service._check_order_form_already_notified(
                new_cart, self.integrated_feature
            )
        )

    def test_order_form_dedup_blocks_when_fingerprint_matches(self):
        items = {"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]}
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config=items,
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config=items,
        )

        self.assertTrue(
            self.service._check_order_form_already_notified(
                new_cart, self.integrated_feature
            )
        )

    def test_order_form_dedup_blocks_when_current_cart_has_no_items(self):
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": []},
        )

        self.assertTrue(
            self.service._check_order_form_already_notified(
                new_cart, self.integrated_feature
            )
        )

    def test_order_form_dedup_allows_when_sku_is_added(self):
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={
                "cart_items": [
                    {"id": "sku-1", "quantity": 1, "price": 1000},
                    {"id": "sku-2", "quantity": 1, "price": 2000},
                ]
            },
        )

        self.assertFalse(
            self.service._check_order_form_already_notified(
                new_cart, self.integrated_feature
            )
        )

    def test_order_form_dedup_skips_previous_cart_without_items(self):
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": []},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )

        self.assertFalse(
            self.service._check_order_form_already_notified(
                new_cart, self.integrated_feature
            )
        )

    def test_order_form_dedup_still_blocks_without_flag(self):
        self.integrated_feature.config = {}
        self.integrated_feature.save(update_fields=["config"])

        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": [{"id": "sku-2", "quantity": 3, "price": 2000}]},
        )

        self.assertTrue(
            self.service._check_order_form_already_notified(
                new_cart, self.integrated_feature
            )
        )

    def test_identical_cart_passes_when_current_cart_has_no_items(self):
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": []},
        )

        self.assertFalse(
            self.service._check_identical_cart_sent_recently(
                new_cart, self.integrated_feature
            )
        )

    def test_identical_cart_passes_when_no_recent_sent_carts(self):
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )

        self.assertFalse(
            self.service._check_identical_cart_sent_recently(
                new_cart, self.integrated_feature
            )
        )

    def test_identical_cart_skips_recent_cart_without_items(self):
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": []},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )

        self.assertFalse(
            self.service._check_identical_cart_sent_recently(
                new_cart, self.integrated_feature
            )
        )

    def test_identical_cart_allows_resend_when_quantities_differ_with_flag(self):
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": [{"id": "sku-1", "quantity": 2, "price": 1000}]},
        )

        self.assertFalse(
            self.service._check_identical_cart_sent_recently(
                new_cart, self.integrated_feature
            )
        )

    def test_identical_cart_blocks_same_sku_and_qty_with_flag(self):
        items = {"cart_items": [{"id": "sku-1", "quantity": 2, "price": 1000}]}
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config=items,
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config=items,
        )

        self.assertTrue(
            self.service._check_identical_cart_sent_recently(
                new_cart, self.integrated_feature
            )
        )

    def test_identical_cart_allows_resend_when_skus_differ_with_flag(self):
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": [{"id": "sku-2", "quantity": 1, "price": 2000}]},
        )

        self.assertFalse(
            self.service._check_identical_cart_sent_recently(
                new_cart, self.integrated_feature
            )
        )

    def test_identical_cart_blocks_same_sku_different_qty_without_flag(self):
        self.integrated_feature.config = {}
        self.integrated_feature.save(update_fields=["config"])

        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": [{"id": "sku-1", "quantity": 2, "price": 1000}]},
        )

        self.assertTrue(
            self.service._check_identical_cart_sent_recently(
                new_cart, self.integrated_feature
            )
        )

    def test_integrated_agent_reads_flag_from_abandoned_cart_config(self):
        items = {"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]}
        self._make_cart(
            self.integrated_agent,
            status="delivered_success",
            config=items,
        )
        new_cart = self._make_cart(
            self.integrated_agent,
            status="created",
            config={"cart_items": [{"id": "sku-2", "quantity": 1, "price": 2000}]},
        )

        self.assertFalse(
            self.service._check_order_form_already_notified(
                new_cart, self.integrated_agent
            )
        )

    def test_integrated_agent_blocks_identical_fingerprint(self):
        items = {"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]}
        self._make_cart(
            self.integrated_agent,
            status="delivered_success",
            config=items,
        )
        new_cart = self._make_cart(
            self.integrated_agent,
            status="created",
            config=items,
        )

        self.assertTrue(
            self.service._check_order_form_already_notified(
                new_cart, self.integrated_agent
            )
        )
        self.assertTrue(
            self.service._check_identical_cart_sent_recently(
                new_cart, self.integrated_agent
            )
        )

    def test_flag_explicitly_false_keeps_order_form_block(self):
        self.integrated_feature.config = {
            ALLOW_RESEND_ON_DIFFERENT_CART_ITEMS_KEY: False
        }
        self.integrated_feature.save(update_fields=["config"])

        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": [{"id": "sku-2", "quantity": 3, "price": 2000}]},
        )

        self.assertTrue(
            self.service._check_order_form_already_notified(
                new_cart, self.integrated_feature
            )
        )

    def test_mark_abandoned_allows_resend_when_flag_on_and_skus_differ(self):
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config={"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config={"cart_items": [{"id": "sku-2", "quantity": 1, "price": 2000}]},
        )

        self.service.notification_lock_service = MagicMock()
        self.service.notification_lock_service.acquire_lock.return_value = True
        self.service._execute_legacy_flow = MagicMock(return_value=True)

        self.service._mark_cart_as_abandoned(
            cart=new_cart,
            order_form={"items": [{"id": "sku-2", "quantity": 1, "price": 2000}]},
            client_profile={"email": "buyer@example.com"},
            integration_config=self.integrated_feature,
        )

        new_cart.refresh_from_db()
        self.assertEqual(new_cart.status, "abandoned")
        self.service._execute_legacy_flow.assert_called_once()

    def test_mark_abandoned_still_skips_when_flag_on_and_fingerprint_matches(self):
        items = {"cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}]}
        self._make_cart(
            self.integrated_feature,
            status="delivered_success",
            config=items,
        )
        new_cart = self._make_cart(
            self.integrated_feature,
            status="created",
            config=items,
        )

        self.service._execute_legacy_flow = MagicMock(return_value=True)
        self.service.clone_order_form_use_case = MagicMock()
        self.service._mark_cart_as_abandoned(
            cart=new_cart,
            order_form={"items": [{"id": "sku-1", "quantity": 1, "price": 1000}]},
            client_profile={"email": "buyer@example.com"},
            integration_config=self.integrated_feature,
        )

        new_cart.refresh_from_db()
        self.assertEqual(new_cart.status, "skipped_order_form_already_notified")
        self.service._execute_legacy_flow.assert_not_called()
        self.service.clone_order_form_use_case.execute.assert_not_called()


class CartItemsFingerprintTests(TestCase):
    def test_without_quantities_compares_sku_ids_only(self):
        fingerprint = CartAbandonmentService._build_cart_items_fingerprint(
            [
                {"id": "sku-1", "quantity": 1},
                {"id": "sku-1", "quantity": 9},
            ],
            include_quantities=False,
        )
        self.assertEqual(fingerprint, frozenset({"sku-1"}))

    def test_with_quantities_treats_qty_change_as_different_cart(self):
        first = CartAbandonmentService._build_cart_items_fingerprint(
            [{"id": "sku-1", "quantity": 1}],
            include_quantities=True,
        )
        second = CartAbandonmentService._build_cart_items_fingerprint(
            [{"id": "sku-1", "quantity": 2}],
            include_quantities=True,
        )
        self.assertNotEqual(first, second)

    def test_missing_or_invalid_quantity_falls_back_to_one(self):
        fingerprint = CartAbandonmentService._build_cart_items_fingerprint(
            [
                {"id": "sku-1"},
                {"id": "sku-2", "quantity": None},
                {"id": "sku-3", "quantity": "abc"},
                {"id": "sku-4", "quantity": 0},
                {"id": "sku-5", "quantity": -2},
            ],
            include_quantities=True,
        )
        self.assertEqual(
            fingerprint,
            frozenset(
                {
                    ("sku-1", 1),
                    ("sku-2", 1),
                    ("sku-3", 1),
                    ("sku-4", 1),
                    ("sku-5", 1),
                }
            ),
        )

    def test_skips_items_without_id(self):
        fingerprint = CartAbandonmentService._build_cart_items_fingerprint(
            [{"quantity": 2}, {"id": "sku-1", "quantity": 1}],
            include_quantities=True,
        )
        self.assertEqual(fingerprint, frozenset({("sku-1", 1)}))
