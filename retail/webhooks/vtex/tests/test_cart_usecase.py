import uuid
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.exceptions import ValidationError

from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.webhooks.vtex.usecases.cart import CartUseCase


class TestCartUseCase(TestCase):
    def setUp(self):
        self.feature = Feature.objects.create(
            can_vtex_integrate=True, code="abandoned_cart"
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="test-account"
        )
        self.user = User.objects.create()

    def test_create_cart_with_phone_restriction_active_allowed(self):
        """Test cart creation when phone restriction is active and phone is allowed."""
        config = {
            "templates_synchronization_status": "synchronized",
            "integration_settings": {
                "abandoned_cart_restriction": {
                    "is_active": True,
                    "phone_numbers": ["5584987654321", "5584987654322"],
                }
            },
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )

        with patch(
            "retail.webhooks.vtex.usecases.cart.CartUseCase._schedule_abandonment_task"
        ):
            cart_use_case = CartUseCase(account="test-account")
            cart_use_case.integrated_feature = integrated_feature

            # Should allow cart creation for allowed phone
            cart = cart_use_case._create_cart("order-123", "5584987654321", "Test User")

            self.assertEqual(cart.order_form_id, "order-123")
            self.assertEqual(cart.phone_number, "5584987654321")
            self.assertEqual(cart.status, "created")

    def test_create_cart_with_phone_restriction_active_blocked(self):
        """Test cart creation when phone restriction is active and phone is blocked."""
        config = {
            "templates_synchronization_status": "synchronized",
            "integration_settings": {
                "abandoned_cart_restriction": {
                    "is_active": True,
                    "phone_numbers": ["5584987654321", "5584987654322"],
                }
            },
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )

        with patch(
            "retail.webhooks.vtex.usecases.cart.CartUseCase._schedule_abandonment_task"
        ):
            cart_use_case = CartUseCase(account="test-account")
            cart_use_case.integrated_feature = integrated_feature

            # Should block cart creation for blocked phone
            with self.assertRaises(ValidationError) as context:
                cart_use_case._create_cart("order-123", "5584987654323", "Test User")

            self.assertEqual(
                context.exception.detail.get("error"),
                "Phone number not allowed due to active restrictions",
            )

    def test_create_cart_with_phone_restriction_active_no_numbers(self):
        """Test cart creation when phone restriction is active but no numbers configured."""
        config = {
            "templates_synchronization_status": "synchronized",
            "integration_settings": {
                "abandoned_cart_restriction": {
                    "is_active": True,
                    "phone_numbers": [],
                }
            },
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )

        with patch(
            "retail.webhooks.vtex.usecases.cart.CartUseCase._schedule_abandonment_task"
        ):
            cart_use_case = CartUseCase(account="test-account")
            cart_use_case.integrated_feature = integrated_feature

            # Should block cart creation when no numbers configured
            with self.assertRaises(ValidationError) as context:
                cart_use_case._create_cart("order-123", "5584987654321", "Test User")

            self.assertEqual(
                context.exception.detail.get("error"),
                "Phone number not allowed due to active restrictions",
            )

    def test_create_cart_with_phone_restriction_inactive(self):
        """Test cart creation when phone restriction is inactive."""
        config = {
            "templates_synchronization_status": "synchronized",
            "integration_settings": {
                "abandoned_cart_restriction": {
                    "is_active": False,
                    "phone_numbers": ["5584987654321"],
                }
            },
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )

        with patch(
            "retail.webhooks.vtex.usecases.cart.CartUseCase._schedule_abandonment_task"
        ):
            cart_use_case = CartUseCase(account="test-account")
            cart_use_case.integrated_feature = integrated_feature

            # Should allow cart creation when restriction is inactive
            cart = cart_use_case._create_cart("order-123", "5584987654322", "Test User")

            self.assertEqual(cart.order_form_id, "order-123")
            self.assertEqual(cart.phone_number, "5584987654322")
            self.assertEqual(cart.status, "created")

    def test_create_cart_with_phone_restriction_missing_config(self):
        """Test cart creation when phone restriction config is missing."""
        config = {
            "templates_synchronization_status": "synchronized",
            "integration_settings": {},
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )

        with patch(
            "retail.webhooks.vtex.usecases.cart.CartUseCase._schedule_abandonment_task"
        ):
            cart_use_case = CartUseCase(account="test-account")
            cart_use_case.integrated_feature = integrated_feature

            # Should allow cart creation when restriction config is missing
            cart = cart_use_case._create_cart("order-123", "5584987654321", "Test User")

            self.assertEqual(cart.order_form_id, "order-123")
            self.assertEqual(cart.phone_number, "5584987654321")
            self.assertEqual(cart.status, "created")

    def test_create_cart_with_normalized_phone_numbers(self):
        """Test cart creation with normalized phone numbers in restriction list."""
        config = {
            "templates_synchronization_status": "synchronized",
            "integration_settings": {
                "abandoned_cart_restriction": {
                    "is_active": True,
                    "phone_numbers": ["+55 84 98765-4321", "(84) 98765-4322"],
                }
            },
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )

        with patch(
            "retail.webhooks.vtex.usecases.cart.CartUseCase._schedule_abandonment_task"
        ):
            cart_use_case = CartUseCase(account="test-account")
            cart_use_case.integrated_feature = integrated_feature

            # Should allow cart creation for normalized numbers that match
            cart = cart_use_case._create_cart("order-123", "5584987654321", "Test User")

            self.assertEqual(cart.order_form_id, "order-123")
            self.assertEqual(cart.phone_number, "5584987654321")
            self.assertEqual(cart.status, "created")

    def test_process_cart_notification_phone_restriction_blocked(self):
        """Test that process_cart_notification raises ValidationError when cart creation is blocked."""
        config = {
            "templates_synchronization_status": "synchronized",
            "integration_settings": {
                "abandoned_cart_restriction": {
                    "is_active": True,
                    "phone_numbers": ["5584987654321"],
                }
            },
        }

        integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature, project=self.project, config=config, user=self.user
        )

        with patch(
            "retail.webhooks.vtex.usecases.cart.CartUseCase._schedule_abandonment_task"
        ):
            cart_use_case = CartUseCase(account="test-account")
            cart_use_case.integrated_feature = integrated_feature

            # Should raise ValidationError when cart creation is blocked
            with self.assertRaises(ValidationError) as context:
                cart_use_case.process_cart_notification(
                    "order-123", "5584987654322", "Test User"
                )

            self.assertEqual(
                context.exception.detail.get("error"),
                "Phone number not allowed due to active restrictions",
            )
            self.assertEqual(context.exception.detail.get("phone"), "5584987654322")
            self.assertEqual(context.exception.detail.get("order_form_id"), "order-123")
