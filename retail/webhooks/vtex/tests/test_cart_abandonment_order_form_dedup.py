import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.webhooks.vtex.services_cart_abandonment_unified import (
    ORDER_FORM_DEDUPLICATION_WINDOW,
    CartAbandonmentService,
)


class CheckOrderFormAlreadyNotifiedTests(TestCase):
    """Tests for the order-form-based deduplication layer."""

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
            config={},
        )
        self.service = CartAbandonmentService()

    def _make_cart(self, **overrides) -> Cart:
        defaults = {
            "order_form_id": "of-1",
            "phone_number": "5511999999999",
            "project": self.project,
            "integrated_feature": self.integrated_feature,
            "config": {},
        }
        defaults.update(overrides)
        return Cart.objects.create(**defaults)

    def test_blocks_when_same_order_form_already_delivered_within_window(self):
        self._make_cart(status="delivered_success")
        new_cart = self._make_cart(status="created")

        self.assertTrue(self.service._check_order_form_already_notified(new_cart))

    def test_passes_when_no_previous_cart_exists(self):
        new_cart = self._make_cart(status="created")

        self.assertFalse(self.service._check_order_form_already_notified(new_cart))

    def test_passes_when_previous_cart_has_different_status(self):
        for status in ("created", "abandoned", "purchased", "empty", "delivered_error"):
            with self.subTest(status=status):
                Cart.objects.filter(project=self.project).delete()
                self._make_cart(status=status)
                new_cart = self._make_cart(status="created")

                self.assertFalse(
                    self.service._check_order_form_already_notified(new_cart)
                )

    def test_passes_when_previous_cart_belongs_to_other_project(self):
        other_project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="other-account"
        )
        Cart.objects.create(
            order_form_id="of-1",
            phone_number="5511999999999",
            project=other_project,
            status="delivered_success",
            config={},
        )
        new_cart = self._make_cart(status="created")

        self.assertFalse(self.service._check_order_form_already_notified(new_cart))

    def test_passes_when_previous_cart_is_outside_window(self):
        old_cart = self._make_cart(status="delivered_success")
        # Force modified_on to a moment older than the dedup window.
        Cart.objects.filter(pk=old_cart.pk).update(
            modified_on=timezone.now()
            - ORDER_FORM_DEDUPLICATION_WINDOW
            - timedelta(hours=1)
        )

        new_cart = self._make_cart(status="created")

        self.assertFalse(self.service._check_order_form_already_notified(new_cart))

    def test_passes_when_cart_has_no_order_form_id(self):
        # Pre-existing delivered_success cart with the same NULL order form
        # should never be treated as a duplicate.
        self._make_cart(order_form_id=None, status="delivered_success")
        new_cart = self._make_cart(order_form_id=None, status="created")

        self.assertFalse(self.service._check_order_form_already_notified(new_cart))

    def test_excludes_the_current_cart_from_the_lookup(self):
        # If, for any reason, the current cart already had delivered_success
        # status (re-processing), the rule must not flag the cart against
        # itself.
        cart = self._make_cart(status="delivered_success")

        self.assertFalse(self.service._check_order_form_already_notified(cart))
