from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.vtex.repositories.cart_repository import CartRepository


class CartRepositoryTest(TestCase):
    """Test cases for CartRepository."""

    def setUp(self):
        """Set up test fixtures."""
        self.project = MagicMock(spec=Project)
        self.project.uuid = uuid4()
        self.order_form_id = "test_order_form_123"
        self.flows_channel_uuid = uuid4()
        self.cart_uuid = uuid4()

    def test_find_by_order_form_cart_found_with_flows_channel(self):
        """Test finding cart when it exists and has flows_channel_uuid."""
        # Arrange
        mock_cart = MagicMock(spec=Cart)
        mock_cart.flows_channel_uuid = self.flows_channel_uuid

        with patch.object(Cart.objects, "filter") as mock_filter:
            mock_filter.return_value.first.return_value = mock_cart

            # Act
            result = CartRepository.find_by_order_form(self.order_form_id, self.project)

            # Assert
            self.assertEqual(result, mock_cart)
            mock_filter.assert_called_once_with(
                order_form_id=self.order_form_id, project=self.project
            )

    def test_find_by_order_form_cart_found_without_flows_channel(self):
        """Test finding cart when it exists but has no flows_channel_uuid."""
        # Arrange
        mock_cart = MagicMock(spec=Cart)
        mock_cart.flows_channel_uuid = None

        with patch.object(Cart.objects, "filter") as mock_filter:
            mock_filter.return_value.first.return_value = mock_cart

            # Act
            result = CartRepository.find_by_order_form(self.order_form_id, self.project)

            # Assert
            self.assertIsNone(result)
            mock_filter.assert_called_once_with(
                order_form_id=self.order_form_id, project=self.project
            )

    def test_find_by_order_form_cart_not_found(self):
        """Test finding cart when it doesn't exist."""
        # Arrange
        with patch.object(Cart.objects, "filter") as mock_filter:
            mock_filter.return_value.first.return_value = None

            # Act
            result = CartRepository.find_by_order_form(self.order_form_id, self.project)

            # Assert
            self.assertIsNone(result)
            mock_filter.assert_called_once_with(
                order_form_id=self.order_form_id, project=self.project
            )

    def test_find_by_order_form_cart_found_with_empty_flows_channel(self):
        """Test finding cart when it exists but flows_channel_uuid is empty string."""
        # Arrange
        mock_cart = MagicMock(spec=Cart)
        mock_cart.flows_channel_uuid = ""

        with patch.object(Cart.objects, "filter") as mock_filter:
            mock_filter.return_value.first.return_value = mock_cart

            # Act
            result = CartRepository.find_by_order_form(self.order_form_id, self.project)

            # Assert
            self.assertIsNone(result)
            mock_filter.assert_called_once_with(
                order_form_id=self.order_form_id, project=self.project
            )

    def test_create_cart_success(self):
        """Test creating a new cart successfully."""
        # Arrange
        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        with patch.object(Cart.objects, "create") as mock_create:
            mock_create.return_value = mock_cart

            # Act
            result = CartRepository.create(
                order_form_id=self.order_form_id,
                project=self.project,
                flows_channel_uuid=self.flows_channel_uuid,
            )

            # Assert
            self.assertEqual(result, mock_cart)
            mock_create.assert_called_once_with(
                order_form_id=self.order_form_id,
                project=self.project,
                flows_channel_uuid=self.flows_channel_uuid,
            )

    def test_create_cart_with_different_flows_channel_uuid(self):
        """Test creating a cart with a different flows_channel_uuid."""
        # Arrange
        different_flows_channel_uuid = uuid4()
        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        with patch.object(Cart.objects, "create") as mock_create:
            mock_create.return_value = mock_cart

            # Act
            result = CartRepository.create(
                order_form_id=self.order_form_id,
                project=self.project,
                flows_channel_uuid=different_flows_channel_uuid,
            )

            # Assert
            self.assertEqual(result, mock_cart)
            mock_create.assert_called_once_with(
                order_form_id=self.order_form_id,
                project=self.project,
                flows_channel_uuid=different_flows_channel_uuid,
            )

    def test_update_status_success(self):
        """Test updating cart status successfully."""
        # Arrange
        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid
        new_status = "purchased"

        # Act
        result = CartRepository.update_status(mock_cart, new_status)

        # Assert
        self.assertEqual(result, mock_cart)
        self.assertEqual(mock_cart.status, new_status)
        mock_cart.save.assert_called_once_with(update_fields=["status", "modified_on"])

    def test_update_status_with_different_status(self):
        """Test updating cart status with a different status."""
        # Arrange
        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid
        new_status = "delivered_success"

        # Act
        result = CartRepository.update_status(mock_cart, new_status)

        # Assert
        self.assertEqual(result, mock_cart)
        self.assertEqual(mock_cart.status, new_status)
        mock_cart.save.assert_called_once_with(update_fields=["status", "modified_on"])

    def test_update_status_with_empty_string(self):
        """Test updating cart status with empty string."""
        # Arrange
        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid
        new_status = ""

        # Act
        result = CartRepository.update_status(mock_cart, new_status)

        # Assert
        self.assertEqual(result, mock_cart)
        self.assertEqual(mock_cart.status, new_status)
        mock_cart.save.assert_called_once_with(update_fields=["status", "modified_on"])

    def test_update_status_with_none(self):
        """Test updating cart status with None."""
        # Arrange
        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid
        new_status = None

        # Act
        result = CartRepository.update_status(mock_cart, new_status)

        # Assert
        self.assertEqual(result, mock_cart)
        self.assertEqual(mock_cart.status, new_status)
        mock_cart.save.assert_called_once_with(update_fields=["status", "modified_on"])

    def test_update_status_multiple_calls(self):
        """Test updating cart status multiple times."""
        # Arrange
        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        # Act
        CartRepository.update_status(mock_cart, "purchased")
        CartRepository.update_status(mock_cart, "delivered_success")
        CartRepository.update_status(mock_cart, "delivered_error")

        # Assert
        self.assertEqual(mock_cart.status, "delivered_error")
        self.assertEqual(mock_cart.save.call_count, 3)
        expected_calls = [
            ({"update_fields": ["status", "modified_on"]},),
            ({"update_fields": ["status", "modified_on"]},),
            ({"update_fields": ["status", "modified_on"]},),
        ]
        mock_cart.save.assert_has_calls(expected_calls)

    def test_find_by_order_form_with_different_project(self):
        """Test finding cart with a different project."""
        # Arrange
        different_project = MagicMock(spec=Project)
        different_project.uuid = uuid4()

        with patch.object(Cart.objects, "filter") as mock_filter:
            mock_filter.return_value.first.return_value = None

            # Act
            result = CartRepository.find_by_order_form(
                self.order_form_id, different_project
            )

            # Assert
            self.assertIsNone(result)
            mock_filter.assert_called_once_with(
                order_form_id=self.order_form_id, project=different_project
            )

    def test_find_by_order_form_with_different_order_form_id(self):
        """Test finding cart with a different order_form_id."""
        # Arrange
        different_order_form_id = "different_order_form_456"

        with patch.object(Cart.objects, "filter") as mock_filter:
            mock_filter.return_value.first.return_value = None

            # Act
            result = CartRepository.find_by_order_form(
                different_order_form_id, self.project
            )

            # Assert
            self.assertIsNone(result)
            mock_filter.assert_called_once_with(
                order_form_id=different_order_form_id, project=self.project
            )

    def test_create_cart_with_empty_order_form_id(self):
        """Test creating a cart with empty order_form_id."""
        # Arrange
        empty_order_form_id = ""
        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        with patch.object(Cart.objects, "create") as mock_create:
            mock_create.return_value = mock_cart

            # Act
            result = CartRepository.create(
                order_form_id=empty_order_form_id,
                project=self.project,
                flows_channel_uuid=self.flows_channel_uuid,
            )

            # Assert
            self.assertEqual(result, mock_cart)
            mock_create.assert_called_once_with(
                order_form_id=empty_order_form_id,
                project=self.project,
                flows_channel_uuid=self.flows_channel_uuid,
            )

    def test_create_cart_with_none_order_form_id(self):
        """Test creating a cart with None order_form_id."""
        # Arrange
        none_order_form_id = None
        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid

        with patch.object(Cart.objects, "create") as mock_create:
            mock_create.return_value = mock_cart

            # Act
            result = CartRepository.create(
                order_form_id=none_order_form_id,
                project=self.project,
                flows_channel_uuid=self.flows_channel_uuid,
            )

            # Assert
            self.assertEqual(result, mock_cart)
            mock_create.assert_called_once_with(
                order_form_id=none_order_form_id,
                project=self.project,
                flows_channel_uuid=self.flows_channel_uuid,
            )

    def test_find_abandoned_cart_for_conversion_found(self):
        """Test finding abandoned cart eligible for conversion."""
        mock_cart = MagicMock(spec=Cart)
        mock_cart.uuid = self.cart_uuid
        mock_cart.notification_sent_at = "2024-01-01T12:00:00Z"

        with patch.object(Cart.objects, "filter") as mock_filter:
            mock_filter.return_value.first.return_value = mock_cart

            result = CartRepository.find_abandoned_cart_for_conversion(
                self.order_form_id, self.project
            )

            self.assertEqual(result, mock_cart)
            mock_filter.assert_called_once_with(
                order_form_id=self.order_form_id,
                project=self.project,
                integrated_agent__isnull=False,
                notification_sent_at__isnull=False,
                capi_notification_sent=False,
            )

    def test_find_abandoned_cart_for_conversion_not_found(self):
        """Test when no abandoned cart is eligible for conversion."""
        with patch.object(Cart.objects, "filter") as mock_filter:
            mock_filter.return_value.first.return_value = None

            result = CartRepository.find_abandoned_cart_for_conversion(
                self.order_form_id, self.project
            )

            self.assertIsNone(result)
            mock_filter.assert_called_once_with(
                order_form_id=self.order_form_id,
                project=self.project,
                integrated_agent__isnull=False,
                notification_sent_at__isnull=False,
                capi_notification_sent=False,
            )

    def test_find_abandoned_cart_for_conversion_already_sent(self):
        """Test that carts with capi_notification_sent=True are not returned."""
        with patch.object(Cart.objects, "filter") as mock_filter:
            mock_filter.return_value.first.return_value = None

            result = CartRepository.find_abandoned_cart_for_conversion(
                self.order_form_id, self.project
            )

            self.assertIsNone(result)
            call_kwargs = mock_filter.call_args[1]
            self.assertEqual(call_kwargs["capi_notification_sent"], False)
