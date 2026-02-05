from django.test import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.services.flows.service import FlowsService
from retail.vtex.repositories.cart_repository import CartRepository
from retail.vtex.usecases.handle_purchase_event import HandlePurchaseEventUseCase
from retail.vtex.usecases.handle_payment_approved import OrderContext


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
        self.mock_cart.capi_notification_sent = False
        self.mock_cart.project = self.mock_project

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

        # Mock JWT token
        self.mock_jwt_token = "mock_jwt_token_12345"

        # Mock JWT generator
        self.mock_jwt_generator = MagicMock()
        self.mock_jwt_generator.generate_jwt_token.return_value = self.mock_jwt_token

    def _create_context(self, order_details=None, project=None):
        """Helper to create OrderContext for tests."""
        return OrderContext(
            order_id=self.order_id,
            project=project or self.mock_project,
            order_details=order_details or self.mock_order_details,
            order_form_id=self.order_form_id,
        )

    def _create_usecase(self):
        """Helper to create usecase with mocked dependencies."""
        return HandlePurchaseEventUseCase(
            flows_service=self.mock_flows_service,
            cart_repository=self.mock_cart_repository,
            jwt_generator=self.mock_jwt_generator,
        )

    def test_execute_successful_purchase_event(self):
        """Test successful execution of purchase event."""
        self.mock_flows_service.send_purchase_event.return_value = self.mock_response
        self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

        usecase = self._create_usecase()
        context = self._create_context()

        usecase.execute(context)

        self.mock_cart_repository.find_by_order_form.assert_called_once_with(
            self.order_form_id, self.mock_project
        )
        self.mock_flows_service.send_purchase_event.assert_called_once()
        self.mock_cart_repository.update_capi_notification_sent.assert_called_once_with(
            self.mock_cart
        )

    def test_execute_cart_not_found(self):
        """Test execution when cart is not found."""
        self.mock_cart_repository.find_by_order_form.return_value = None

        usecase = self._create_usecase()
        context = self._create_context()

        usecase.execute(context)

        self.mock_cart_repository.find_by_order_form.assert_called_once()
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_cart_already_notified(self):
        """Test execution when cart notification was already sent."""
        notified_cart = MagicMock(spec=Cart)
        notified_cart.uuid = self.cart_uuid
        notified_cart.capi_notification_sent = True

        self.mock_cart_repository.find_by_order_form.return_value = notified_cart

        usecase = self._create_usecase()
        context = self._create_context()

        usecase.execute(context)

        self.mock_cart_repository.find_by_order_form.assert_called_once()
        self.mock_flows_service.send_purchase_event.assert_not_called()
        self.mock_cart_repository.update_capi_notification_sent.assert_not_called()

    def test_execute_flows_service_failure(self):
        """Test execution when Flows service returns error."""
        failed_response = MagicMock()
        failed_response.status_code = 500

        self.mock_flows_service.send_purchase_event.return_value = failed_response
        self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

        usecase = self._create_usecase()
        context = self._create_context()

        usecase.execute(context)

        self.mock_flows_service.send_purchase_event.assert_called_once()
        self.mock_cart_repository.update_capi_notification_sent.assert_not_called()

    def test_execute_no_phone_number(self):
        """Test execution when no phone number is found in order details."""
        order_details_without_phone = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {},
            "storePreferencesData": {"currencyCode": "BRL"},
            "value": 10000,
        }

        self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

        usecase = self._create_usecase()
        context = self._create_context(order_details=order_details_without_phone)

        usecase.execute(context)

        self.mock_cart_repository.update_capi_notification_sent.assert_not_called()
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_with_different_currency(self):
        """Test execution with different currency."""
        order_details_usd = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {"phone": self.phone_number},
            "storePreferencesData": {"currencyCode": "USD"},
            "value": 5000,
        }

        self.mock_flows_service.send_purchase_event.return_value = self.mock_response
        self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

        usecase = self._create_usecase()
        context = self._create_context(order_details=order_details_usd)

        usecase.execute(context)

        self.mock_flows_service.send_purchase_event.assert_called_once()
        call_args = self.mock_flows_service.send_purchase_event.call_args[0][0]
        self.assertEqual(call_args["payload"]["currency"], "USD")
        self.assertEqual(call_args["payload"]["value"], 50.0)

    def test_execute_with_default_currency(self):
        """Test execution when currency is not specified (should default to BRL)."""
        order_details_no_currency = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {"phone": self.phone_number},
            "storePreferencesData": {},
            "value": 7500,
        }

        self.mock_flows_service.send_purchase_event.return_value = self.mock_response
        self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

        usecase = self._create_usecase()
        context = self._create_context(order_details=order_details_no_currency)

        usecase.execute(context)

        self.mock_flows_service.send_purchase_event.assert_called_once()
        call_args = self.mock_flows_service.send_purchase_event.call_args[0][0]
        self.assertEqual(call_args["payload"]["currency"], "BRL")
        self.assertEqual(call_args["payload"]["value"], 75.0)

    def test_execute_payload_structure(self):
        """Test that the payload sent to Flows has the correct structure."""
        self.mock_flows_service.send_purchase_event.return_value = self.mock_response
        self.mock_cart_repository.find_by_order_form.return_value = self.mock_cart

        usecase = self._create_usecase()
        context = self._create_context()

        usecase.execute(context)

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
        usecase = HandlePurchaseEventUseCase()

        self.assertIsInstance(usecase.flows_service, FlowsService)
        self.assertIsInstance(usecase.cart_repository, CartRepository)

    def test_init_with_custom_services(self):
        """Test initialization with custom services."""
        custom_flows_service = MagicMock(spec=FlowsService)
        custom_cart_repository = MagicMock(spec=CartRepository)

        usecase = HandlePurchaseEventUseCase(
            flows_service=custom_flows_service,
            cart_repository=custom_cart_repository,
        )

        self.assertEqual(usecase.flows_service, custom_flows_service)
        self.assertEqual(usecase.cart_repository, custom_cart_repository)
