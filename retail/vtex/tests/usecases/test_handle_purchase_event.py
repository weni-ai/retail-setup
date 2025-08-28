from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.services.flows.service import FlowsService
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.repositories.cart_repository import CartRepository
from retail.vtex.usecases.handle_purchase_event import HandlePurchaseEventUseCase


class HandlePurchaseEventUseCaseTest(TestCase):
    """Test cases for HandlePurchaseEventUseCase."""

    def setUp(self):
        """Set up test fixtures."""
        self.order_id = "test_order_123"
        self.project_uuid = uuid4()
        self.order_form_id = "test_order_form_456"
        self.cart_uuid = uuid4()
        self.flows_channel_uuid = uuid4()
        self.phone_number = "5511999999999"

        # Mock services
        self.mock_vtex_io_service = MagicMock(spec=VtexIOService)
        self.mock_flows_service = MagicMock(spec=FlowsService)
        self.mock_cart_repository = MagicMock(spec=CartRepository)

        # Mock project
        self.mock_project = MagicMock(spec=Project)
        self.mock_project.uuid = self.project_uuid
        self.mock_project.vtex_account = "test_account"

        # Mock cart
        self.mock_cart = MagicMock(spec=Cart)
        self.mock_cart.uuid = self.cart_uuid
        self.mock_cart.flows_channel_uuid = self.flows_channel_uuid
        self.mock_cart.status = "created"

        # Mock order details
        self.mock_order_details = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {"phone": self.phone_number},
            "storePreferencesData": {"currencyCode": "BRL"},
            "value": 10000,  # 100.00 in cents
        }

        # Mock response
        self.mock_response = MagicMock()
        self.mock_response.status_code = 200

    def test_execute_successful_purchase_event(self):
        """Test successful execution of purchase event."""
        # Arrange
        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = self.mock_project

            self.mock_flows_service.send_purchase_event.return_value = (
                self.mock_response
            )

            usecase = HandlePurchaseEventUseCase(
                vtex_io_service=self.mock_vtex_io_service,
                flows_service=self.mock_flows_service,
                cart_repository=self.mock_cart_repository,
            )

            self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                self.mock_order_details
            )
            self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

            # Act
            usecase.execute(self.order_id, str(self.project_uuid))

            # Assert
            self.mock_vtex_io_service.get_order_details_by_id.assert_called_once_with(
                f"{self.mock_project.vtex_account}.myvtex.com", self.order_id
            )
            self.mock_cart_repository.find_by_order_form.assert_called_once_with(
                self.order_form_id, self.mock_project
            )
            self.mock_cart_repository.update_status.assert_called_once_with(
                self.mock_cart, "purchased"
            )
            self.mock_flows_service.send_purchase_event.assert_called_once()

    def test_execute_project_not_found(self):
        """Test execution when project is not found."""
        # Arrange
        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = None

            with patch.object(Project.objects, "get", side_effect=Project.DoesNotExist):
                usecase = HandlePurchaseEventUseCase(
                    vtex_io_service=self.mock_vtex_io_service,
                    flows_service=self.mock_flows_service,
                    cart_repository=self.mock_cart_repository,
                )

                # Act
                usecase.execute(self.order_id, str(self.project_uuid))

                # Assert
                self.mock_vtex_io_service.get_order_details_by_id.assert_not_called()
                self.mock_cart_repository.find_by_order_form.assert_not_called()
                self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_project_from_cache(self):
        """Test execution when project is found in cache."""
        # Arrange
        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = self.mock_project

            self.mock_flows_service.send_purchase_event.return_value = (
                self.mock_response
            )

            usecase = HandlePurchaseEventUseCase(
                vtex_io_service=self.mock_vtex_io_service,
                flows_service=self.mock_flows_service,
                cart_repository=self.mock_cart_repository,
            )

            self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                self.mock_order_details
            )
            self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

            # Act
            usecase.execute(self.order_id, str(self.project_uuid))

            # Assert
            mock_cache.get.assert_called_once_with(
                f"project_by_uuid_{self.project_uuid}"
            )
            self.mock_vtex_io_service.get_order_details_by_id.assert_called_once()

    def test_execute_project_multiple_objects_returned(self):
        """Test execution when multiple projects are found."""
        # Arrange
        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = None

            with patch.object(
                Project.objects, "get", side_effect=Project.MultipleObjectsReturned
            ):
                usecase = HandlePurchaseEventUseCase(
                    vtex_io_service=self.mock_vtex_io_service,
                    flows_service=self.mock_flows_service,
                    cart_repository=self.mock_cart_repository,
                )

                # Act
                usecase.execute(self.order_id, str(self.project_uuid))

                # Assert
                self.mock_vtex_io_service.get_order_details_by_id.assert_not_called()
                self.mock_cart_repository.find_by_order_form.assert_not_called()
                self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_order_not_found(self):
        """Test execution when order is not found in VTEX."""
        # Arrange
        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = self.mock_project

            usecase = HandlePurchaseEventUseCase(
                vtex_io_service=self.mock_vtex_io_service,
                flows_service=self.mock_flows_service,
                cart_repository=self.mock_cart_repository,
            )

            self.mock_vtex_io_service.get_order_details_by_id.return_value = None

            # Act
            usecase.execute(self.order_id, str(self.project_uuid))

            # Assert
            self.mock_vtex_io_service.get_order_details_by_id.assert_called_once()
            self.mock_cart_repository.find_by_order_form.assert_not_called()
            self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_no_order_form_id(self):
        """Test execution when order_form_id is not found in order details."""
        # Arrange
        order_details_without_form_id = {
            "clientProfileData": {"phone": self.phone_number},
            "storePreferencesData": {"currencyCode": "BRL"},
            "value": 10000,
        }

        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = self.mock_project

            usecase = HandlePurchaseEventUseCase(
                vtex_io_service=self.mock_vtex_io_service,
                flows_service=self.mock_flows_service,
                cart_repository=self.mock_cart_repository,
            )

            self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                order_details_without_form_id
            )

            # Act
            usecase.execute(self.order_id, str(self.project_uuid))

            # Assert
            self.mock_vtex_io_service.get_order_details_by_id.assert_called_once()
            self.mock_cart_repository.find_by_order_form.assert_not_called()
            self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_cart_not_found(self):
        """Test execution when cart is not found."""
        # Arrange
        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = self.mock_project

            usecase = HandlePurchaseEventUseCase(
                vtex_io_service=self.mock_vtex_io_service,
                flows_service=self.mock_flows_service,
                cart_repository=self.mock_cart_repository,
            )

            self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                self.mock_order_details
            )
            self.mock_cart_repository.find_by_order_form.return_value = None

            # Act
            usecase.execute(self.order_id, str(self.project_uuid))

            # Assert
            self.mock_vtex_io_service.get_order_details_by_id.assert_called_once()
            self.mock_cart_repository.find_by_order_form.assert_called_once()
            self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_cart_already_purchased(self):
        """Test execution when cart is already marked as purchased."""
        # Arrange
        purchased_cart = MagicMock(spec=Cart)
        purchased_cart.uuid = self.cart_uuid
        purchased_cart.status = "purchased"

        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = self.mock_project

            usecase = HandlePurchaseEventUseCase(
                vtex_io_service=self.mock_vtex_io_service,
                flows_service=self.mock_flows_service,
                cart_repository=self.mock_cart_repository,
            )

            self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                self.mock_order_details
            )
            self.mock_cart_repository.find_by_order_form.return_value = purchased_cart

            # Act
            usecase.execute(self.order_id, str(self.project_uuid))

            # Assert
            self.mock_vtex_io_service.get_order_details_by_id.assert_called_once()
            self.mock_cart_repository.find_by_order_form.assert_called_once()
            self.mock_cart_repository.update_status.assert_not_called()
            self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_flows_service_failure(self):
        """Test execution when Flows service returns error."""
        # Arrange
        failed_response = MagicMock()
        failed_response.status_code = 500

        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = self.mock_project

            self.mock_flows_service.send_purchase_event.return_value = failed_response

            usecase = HandlePurchaseEventUseCase(
                vtex_io_service=self.mock_vtex_io_service,
                flows_service=self.mock_flows_service,
                cart_repository=self.mock_cart_repository,
            )

            self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                self.mock_order_details
            )
            self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

            # Act
            usecase.execute(self.order_id, str(self.project_uuid))

            # Assert
            self.mock_cart_repository.update_status.assert_called_once_with(
                self.mock_cart, "purchased"
            )
            self.mock_flows_service.send_purchase_event.assert_called_once()

    def test_execute_no_phone_number(self):
        """Test execution when no phone number is found in order details."""
        # Arrange
        order_details_without_phone = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {},
            "storePreferencesData": {"currencyCode": "BRL"},
            "value": 10000,
        }

        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = self.mock_project

            usecase = HandlePurchaseEventUseCase(
                vtex_io_service=self.mock_vtex_io_service,
                flows_service=self.mock_flows_service,
                cart_repository=self.mock_cart_repository,
            )

            self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                order_details_without_phone
            )
            self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

            # Act
            usecase.execute(self.order_id, str(self.project_uuid))

            # Assert
            self.mock_cart_repository.update_status.assert_called_once_with(
                self.mock_cart, "purchased"
            )
            # The method still calls _send_to_flows with None payload
            self.mock_flows_service.send_purchase_event.assert_called_once_with(None)

    def test_execute_with_different_currency(self):
        """Test execution with different currency."""
        # Arrange
        order_details_usd = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {"phone": self.phone_number},
            "storePreferencesData": {"currencyCode": "USD"},
            "value": 5000,  # 50.00 in cents
        }

        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = self.mock_project

            self.mock_flows_service.send_purchase_event.return_value = (
                self.mock_response
            )

            usecase = HandlePurchaseEventUseCase(
                vtex_io_service=self.mock_vtex_io_service,
                flows_service=self.mock_flows_service,
                cart_repository=self.mock_cart_repository,
            )

            self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                order_details_usd
            )
            self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

            # Act
            usecase.execute(self.order_id, str(self.project_uuid))

            # Assert
            self.mock_flows_service.send_purchase_event.assert_called_once()
            call_args = self.mock_flows_service.send_purchase_event.call_args[0][0]
            self.assertEqual(call_args["payload"]["currency"], "USD")
            self.assertEqual(call_args["payload"]["value"], 50.0)

    def test_execute_with_default_currency(self):
        """Test execution when currency is not specified (should default to BRL)."""
        # Arrange
        order_details_no_currency = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {"phone": self.phone_number},
            "storePreferencesData": {},
            "value": 7500,  # 75.00 in cents
        }

        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = self.mock_project

            self.mock_flows_service.send_purchase_event.return_value = (
                self.mock_response
            )

            usecase = HandlePurchaseEventUseCase(
                vtex_io_service=self.mock_vtex_io_service,
                flows_service=self.mock_flows_service,
                cart_repository=self.mock_cart_repository,
            )

            self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                order_details_no_currency
            )
            self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

            # Act
            usecase.execute(self.order_id, str(self.project_uuid))

            # Assert
            self.mock_flows_service.send_purchase_event.assert_called_once()
            call_args = self.mock_flows_service.send_purchase_event.call_args[0][0]
            self.assertEqual(call_args["payload"]["currency"], "BRL")
            self.assertEqual(call_args["payload"]["value"], 75.0)

    def test_execute_payload_structure(self):
        """Test that the payload sent to Flows has the correct structure."""
        # Arrange
        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            mock_cache.get.return_value = self.mock_project

            self.mock_flows_service.send_purchase_event.return_value = (
                self.mock_response
            )

            usecase = HandlePurchaseEventUseCase(
                vtex_io_service=self.mock_vtex_io_service,
                flows_service=self.mock_flows_service,
                cart_repository=self.mock_cart_repository,
            )

            self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                self.mock_order_details
            )
            self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

            # Act
            usecase.execute(self.order_id, str(self.project_uuid))

            # Assert
            self.mock_flows_service.send_purchase_event.assert_called_once()
            call_args = self.mock_flows_service.send_purchase_event.call_args[0][0]

            expected_payload = {
                "event_type": "purchase",
                "contact_urn": f"whatsapp:{self.phone_number}",
                "channel_uuid": str(self.flows_channel_uuid),
                "payload": {
                    "order_form_id": self.order_form_id,
                    "value": 100.0,
                    "currency": "BRL",
                },
            }

            self.assertEqual(call_args, expected_payload)

    def test_init_with_default_services(self):
        """Test initialization with default services."""
        # Arrange & Act
        usecase = HandlePurchaseEventUseCase()

        # Assert
        self.assertIsInstance(usecase.vtex_io_service, VtexIOService)
        self.assertIsInstance(usecase.flows_service, FlowsService)
        self.assertIsInstance(usecase.cart_repository, CartRepository)

    def test_init_with_custom_services(self):
        """Test initialization with custom services."""
        # Arrange
        custom_vtex_service = MagicMock(spec=VtexIOService)
        custom_flows_service = MagicMock(spec=FlowsService)
        custom_cart_repository = MagicMock(spec=CartRepository)

        # Act
        usecase = HandlePurchaseEventUseCase(
            vtex_io_service=custom_vtex_service,
            flows_service=custom_flows_service,
            cart_repository=custom_cart_repository,
        )

        # Assert
        self.assertEqual(usecase.vtex_io_service, custom_vtex_service)
        self.assertEqual(usecase.flows_service, custom_flows_service)
        self.assertEqual(usecase.cart_repository, custom_cart_repository)

    def test_execute_project_from_database_cache_miss(self):
        """Test execution when project is not in cache and needs to be fetched from database."""
        # Arrange
        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            # Cache miss - returns None
            mock_cache.get.return_value = None

            # Mock database query
            with patch.object(Project.objects, "get", return_value=self.mock_project):
                self.mock_flows_service.send_purchase_event.return_value = (
                    self.mock_response
                )

                usecase = HandlePurchaseEventUseCase(
                    vtex_io_service=self.mock_vtex_io_service,
                    flows_service=self.mock_flows_service,
                    cart_repository=self.mock_cart_repository,
                )

                self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                    self.mock_order_details
                )
                self.mock_cart_repository.find_by_order_form.return_value = (
                    self.mock_cart
                )

                # Act
                usecase.execute(self.order_id, str(self.project_uuid))

                # Assert
                # Verify cache was checked
                mock_cache.get.assert_called_once_with(
                    f"project_by_uuid_{self.project_uuid}"
                )
                # Verify database was queried
                Project.objects.get.assert_called_once_with(uuid=str(self.project_uuid))
                # Verify project was cached
                mock_cache.set.assert_called_once_with(
                    f"project_by_uuid_{self.project_uuid}",
                    self.mock_project,
                    timeout=43200,
                )
                # Verify the rest of the flow executed
                self.mock_vtex_io_service.get_order_details_by_id.assert_called_once()
                self.mock_cart_repository.find_by_order_form.assert_called_once()
                self.mock_flows_service.send_purchase_event.assert_called_once()

    def test_execute_project_from_database_cache_miss_with_different_uuid(self):
        """Test execution with different project UUID to ensure cache key uniqueness."""
        # Arrange
        different_project_uuid = uuid4()
        different_mock_project = MagicMock(spec=Project)
        different_mock_project.uuid = different_project_uuid
        different_mock_project.vtex_account = "different_account"

        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            # Cache miss - returns None
            mock_cache.get.return_value = None

            # Mock database query
            with patch.object(
                Project.objects, "get", return_value=different_mock_project
            ):
                self.mock_flows_service.send_purchase_event.return_value = (
                    self.mock_response
                )

                usecase = HandlePurchaseEventUseCase(
                    vtex_io_service=self.mock_vtex_io_service,
                    flows_service=self.mock_flows_service,
                    cart_repository=self.mock_cart_repository,
                )

                self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                    self.mock_order_details
                )
                self.mock_cart_repository.find_by_order_form.return_value = (
                    self.mock_cart
                )

                # Act
                usecase.execute(self.order_id, str(different_project_uuid))

                # Assert
                # Verify cache was checked with correct key
                mock_cache.get.assert_called_once_with(
                    f"project_by_uuid_{different_project_uuid}"
                )
                # Verify database was queried with correct UUID
                Project.objects.get.assert_called_once_with(
                    uuid=str(different_project_uuid)
                )
                # Verify project was cached with correct key
                mock_cache.set.assert_called_once_with(
                    f"project_by_uuid_{different_project_uuid}",
                    different_mock_project,
                    timeout=43200,
                )

    def test_execute_project_cache_set_timeout(self):
        """Test that the cache timeout is set correctly to 12 hours (43200 seconds)."""
        # Arrange
        with patch("retail.vtex.usecases.handle_purchase_event.cache") as mock_cache:
            # Cache miss - returns None
            mock_cache.get.return_value = None

            # Mock database query
            with patch.object(Project.objects, "get", return_value=self.mock_project):
                usecase = HandlePurchaseEventUseCase(
                    vtex_io_service=self.mock_vtex_io_service,
                    flows_service=self.mock_flows_service,
                    cart_repository=self.mock_cart_repository,
                )

                self.mock_vtex_io_service.get_order_details_by_id.return_value = (
                    self.mock_order_details
                )
                self.mock_cart_repository.find_by_order_form.return_value = (
                    self.mock_cart
                )

                # Act
                usecase.execute(self.order_id, str(self.project_uuid))

                # Assert
                # Verify cache.set was called with correct timeout
                mock_cache.set.assert_called_once()
                call_args = mock_cache.set.call_args
                # Check positional arguments
                self.assertEqual(
                    call_args[0][0], f"project_by_uuid_{self.project_uuid}"
                )
                self.assertEqual(call_args[0][1], self.mock_project)
                # Check keyword arguments for timeout
                self.assertEqual(call_args[1]["timeout"], 43200)  # 12 hours in seconds
