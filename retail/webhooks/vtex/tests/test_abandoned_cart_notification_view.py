import uuid
from unittest.mock import patch, Mock

from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status

from retail.features.models import Feature
from retail.projects.models import Project

from retail.webhooks.vtex.views.abandoned_cart_notification import (
    AbandonedCartNotification,
)


class TestAbandonedCartNotificationView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.feature = Feature.objects.create(
            can_vtex_integrate=True, code="abandoned_cart"
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="test-account"
        )
        self.user = User.objects.create()

    @patch("retail.webhooks.vtex.views.abandoned_cart_notification.CartUseCase")
    def test_phone_restriction_blocked_response(self, mock_cart_use_case):
        """Test that the view returns appropriate response when phone is blocked by restriction."""
        # Mock the CartUseCase to raise ValidationError for phone restriction
        mock_instance = Mock()
        mock_instance.project = self.project
        mock_instance.integrated_feature = Mock()

        from rest_framework.exceptions import ValidationError

        mock_instance.process_cart_notification.side_effect = ValidationError(
            {
                "error": "Phone number not allowed due to active restrictions",
                "phone": "5584987654321",
                "order_form_id": "order-123",
                "project_uuid": str(self.project.uuid),
                "message": "Cart creation blocked due to active phone restrictions.",
            }
        )

        mock_cart_use_case.return_value = mock_instance

        # Create the view instance and test directly
        view = AbandonedCartNotification()
        view.request = Mock()
        view.request.data = {
            "cart_id": "order-123",
            "phone": "5584987654321",
            "name": "Test User",
            "account": "test-account",
        }

        # Mock the serializer validation
        with patch(
            "retail.webhooks.vtex.views.abandoned_cart_notification.CartSerializer"
        ) as mock_serializer:
            mock_serializer_instance = Mock()
            mock_serializer_instance.validated_data = {
                "cart_id": "order-123",
                "phone": "5584987654321",
                "name": "Test User",
                "account": "test-account",
            }
            mock_serializer.return_value = mock_serializer_instance

            # Should raise ValidationError with HTTP 400
            with self.assertRaises(ValidationError) as context:
                view.post(view.request)

            # Check the error details
            error_detail = context.exception.detail
            self.assertEqual(
                error_detail.get("error"),
                "Phone number not allowed due to active restrictions",
            )
            self.assertEqual(error_detail.get("phone"), "5584987654321")
            self.assertEqual(error_detail.get("order_form_id"), "order-123")
            self.assertEqual(
                error_detail.get("message"),
                "Cart creation blocked due to active phone restrictions.",
            )

    @patch("retail.webhooks.vtex.views.abandoned_cart_notification.CartUseCase")
    def test_phone_restriction_allowed_response(self, mock_cart_use_case):
        """Test that the view returns success response when phone is allowed."""
        # Mock the CartUseCase to return a successful cart
        mock_instance = Mock()
        mock_instance.project = self.project
        mock_instance.integrated_feature = Mock()

        mock_cart = Mock()
        mock_cart.uuid = uuid.uuid4()
        mock_cart.order_form_id = "order-123"
        mock_cart.status = "created"

        mock_instance.process_cart_notification.return_value = mock_cart

        mock_cart_use_case.return_value = mock_instance

        # Create the view instance and test directly
        view = AbandonedCartNotification()
        view.request = Mock()
        view.request.data = {
            "cart_id": "order-123",
            "phone": "5584987654321",
            "name": "Test User",
            "account": "test-account",
        }

        # Mock the serializer validation
        with patch(
            "retail.webhooks.vtex.views.abandoned_cart_notification.CartSerializer"
        ) as mock_serializer:
            mock_serializer_instance = Mock()
            mock_serializer_instance.validated_data = {
                "cart_id": "order-123",
                "phone": "5584987654321",
                "name": "Test User",
                "account": "test-account",
            }
            mock_serializer.return_value = mock_serializer_instance

            response = view.post(view.request)

        # Should return 200 OK with success message
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("message"), "Cart processed successfully.")
        self.assertEqual(response.data.get("cart_id"), "order-123")
        self.assertEqual(response.data.get("status"), "created")

    @patch("retail.webhooks.vtex.views.abandoned_cart_notification.CartUseCase")
    def test_other_validation_error_still_raised(self, mock_cart_use_case):
        """Test that other ValidationErrors are still raised normally."""
        # Mock the CartUseCase to raise a different ValidationError
        mock_instance = Mock()
        mock_instance.project = self.project
        mock_instance.integrated_feature = Mock()

        from rest_framework.exceptions import ValidationError

        mock_instance.process_cart_notification.side_effect = ValidationError(
            {"error": "Templates are not synchronized"}
        )

        mock_cart_use_case.return_value = mock_instance

        # Create the view instance and test directly
        view = AbandonedCartNotification()
        view.request = Mock()
        view.request.data = {
            "cart_id": "order-123",
            "phone": "5584987654321",
            "name": "Test User",
            "account": "test-account",
        }

        # Mock the serializer validation
        with patch(
            "retail.webhooks.vtex.views.abandoned_cart_notification.CartSerializer"
        ) as mock_serializer:
            mock_serializer_instance = Mock()
            mock_serializer_instance.validated_data = {
                "cart_id": "order-123",
                "phone": "5584987654321",
                "name": "Test User",
                "account": "test-account",
            }
            mock_serializer.return_value = mock_serializer_instance

            # Should raise the ValidationError normally
            with self.assertRaises(ValidationError) as context:
                view.post(view.request)

            # Check that it's the expected error
            error_detail = context.exception.detail
            self.assertEqual(
                error_detail.get("error"), "Templates are not synchronized"
            )

    @patch("retail.webhooks.vtex.views.abandoned_cart_notification.CartUseCase")
    def test_phone_normalization_in_view(self, mock_cart_use_case):
        """Test that phone numbers are normalized in the view."""
        # Mock the CartUseCase
        mock_instance = Mock()
        mock_instance.project = self.project
        mock_instance.integrated_feature = Mock()

        mock_cart = Mock()
        mock_cart.uuid = uuid.uuid4()
        mock_cart.order_form_id = "order-123"
        mock_cart.status = "created"

        mock_instance.process_cart_notification.return_value = mock_cart

        mock_cart_use_case.return_value = mock_instance

        # Create the view instance and test directly
        view = AbandonedCartNotification()
        view.request = Mock()
        view.request.data = {
            "cart_id": "order-123",
            "phone": "+55 (84) 98765-4321",
            "name": "Test User",
            "account": "test-account",
        }

        # Mock the serializer validation
        with patch(
            "retail.webhooks.vtex.views.abandoned_cart_notification.CartSerializer"
        ) as mock_serializer:
            mock_serializer_instance = Mock()
            mock_serializer_instance.validated_data = {
                "cart_id": "order-123",
                "phone": "+55 (84) 98765-4321",
                "name": "Test User",
                "account": "test-account",
            }
            mock_serializer.return_value = mock_serializer_instance

            response = view.post(view.request)

        # Should return success and the normalized phone number
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("message"), "Cart processed successfully.")

        # Verify that the normalized phone was passed to the use case
        mock_instance.process_cart_notification.assert_called_once()
        call_args = mock_instance.process_cart_notification.call_args
        self.assertEqual(call_args[0][1], "5584987654321")  # Normalized phone
