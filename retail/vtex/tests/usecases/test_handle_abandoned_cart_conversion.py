from django.test import TestCase
from django.utils import timezone
from unittest.mock import MagicMock
from uuid import uuid4

from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.services.flows.service import FlowsService
from retail.vtex.repositories.cart_repository import CartRepository
from retail.vtex.usecases.handle_abandoned_cart_conversion import (
    HandleAbandonedCartConversionUseCase,
)
from retail.vtex.usecases.handle_payment_approved import OrderContext
from retail.agents.domains.agent_integration.models import IntegratedAgent


class HandleAbandonedCartConversionUseCaseTest(TestCase):
    """Test cases for HandleAbandonedCartConversionUseCase."""

    def setUp(self):
        """Set up test fixtures."""
        self.order_id = "test_order_123"
        self.project_uuid = uuid4()
        self.order_form_id = "test_order_form_456"
        self.cart_uuid = uuid4()
        self.channel_uuid = uuid4()
        self.phone_number = "5511999999999"
        self.notification_sent_at = timezone.now()

        # Mock services
        self.mock_flows_service = MagicMock(spec=FlowsService)
        self.mock_cart_repository = MagicMock(spec=CartRepository)

        # Mock project
        self.mock_project = MagicMock(spec=Project)
        self.mock_project.uuid = self.project_uuid
        self.mock_project.vtex_account = "test_account"

        # Mock integrated agent
        self.mock_integrated_agent = MagicMock(spec=IntegratedAgent)
        self.mock_integrated_agent.channel_uuid = self.channel_uuid

        # Mock cart
        self.mock_cart = MagicMock(spec=Cart)
        self.mock_cart.uuid = self.cart_uuid
        self.mock_cart.phone_number = self.phone_number
        self.mock_cart.notification_sent_at = self.notification_sent_at
        self.mock_cart.project = self.mock_project
        self.mock_cart.integrated_agent = self.mock_integrated_agent

        # Order created after notification
        self.mock_order_details = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {"phone": self.phone_number},
            "storePreferencesData": {"currencyCode": "BRL"},
            "value": 10000,
            "creationDate": (
                self.notification_sent_at + timezone.timedelta(hours=1)
            ).isoformat(),
        }

        # Mock response
        self.mock_response = MagicMock()
        self.mock_response.status_code = 200

        # Mock JWT
        self.mock_jwt_generator = MagicMock()
        self.mock_jwt_generator.generate_jwt_token.return_value = "mock_jwt_token"

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
        return HandleAbandonedCartConversionUseCase(
            flows_service=self.mock_flows_service,
            cart_repository=self.mock_cart_repository,
            jwt_generator=self.mock_jwt_generator,
        )

    def test_execute_successful_conversion(self):
        """Test successful conversion detection and reporting."""
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )
        self.mock_flows_service.send_purchase_event.return_value = self.mock_response

        usecase = self._create_usecase()
        context = self._create_context()

        result = usecase.execute(context)

        self.assertTrue(result)
        self.mock_cart_repository.find_abandoned_cart_for_conversion.assert_called_once_with(
            self.order_form_id, self.mock_project
        )
        self.mock_flows_service.send_purchase_event.assert_called_once()

    def test_execute_no_eligible_cart(self):
        """Test when no eligible abandoned cart is found."""
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = None

        usecase = self._create_usecase()
        context = self._create_context()

        result = usecase.execute(context)

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_order_before_notification(self):
        """Test when order was placed before notification was sent."""
        # Order created BEFORE notification
        order_details_before = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {"phone": self.phone_number},
            "storePreferencesData": {"currencyCode": "BRL"},
            "value": 10000,
            "creationDate": (
                self.notification_sent_at - timezone.timedelta(hours=1)
            ).isoformat(),
        }

        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        usecase = self._create_usecase()
        context = self._create_context(order_details=order_details_before)

        result = usecase.execute(context)

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_no_creation_date(self):
        """Test when order has no creation date."""
        order_details_no_date = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {"phone": self.phone_number},
            "storePreferencesData": {"currencyCode": "BRL"},
            "value": 10000,
        }

        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        usecase = self._create_usecase()
        context = self._create_context(order_details=order_details_no_date)

        result = usecase.execute(context)

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_no_channel_uuid(self):
        """Test when cart has no channel_uuid."""
        cart_no_channel = MagicMock(spec=Cart)
        cart_no_channel.uuid = self.cart_uuid
        cart_no_channel.notification_sent_at = self.notification_sent_at
        cart_no_channel.project = self.mock_project
        cart_no_channel.integrated_agent = None

        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            cart_no_channel
        )

        usecase = self._create_usecase()
        context = self._create_context()

        result = usecase.execute(context)

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_no_phone(self):
        """Test when no phone number is available."""
        order_details_no_phone = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {},
            "storePreferencesData": {"currencyCode": "BRL"},
            "value": 10000,
            "creationDate": (
                self.notification_sent_at + timezone.timedelta(hours=1)
            ).isoformat(),
        }

        cart_no_phone = MagicMock(spec=Cart)
        cart_no_phone.uuid = self.cart_uuid
        cart_no_phone.phone_number = None
        cart_no_phone.notification_sent_at = self.notification_sent_at
        cart_no_phone.project = self.mock_project
        cart_no_phone.integrated_agent = self.mock_integrated_agent

        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            cart_no_phone
        )

        usecase = self._create_usecase()
        context = self._create_context(order_details=order_details_no_phone)

        result = usecase.execute(context)

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_flows_service_failure(self):
        """Test when Flows service returns error."""
        failed_response = MagicMock()
        failed_response.status_code = 500

        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )
        self.mock_flows_service.send_purchase_event.return_value = failed_response

        usecase = self._create_usecase()
        context = self._create_context()

        result = usecase.execute(context)

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_called_once()

    def test_execute_payload_structure(self):
        """Test that the payload has the correct structure."""
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )
        self.mock_flows_service.send_purchase_event.return_value = self.mock_response

        usecase = self._create_usecase()
        context = self._create_context()

        usecase.execute(context)

        call_args = self.mock_flows_service.send_purchase_event.call_args[0][0]

        self.assertEqual(call_args["event_type"], "abandoned_cart_conversion")
        self.assertEqual(call_args["contact_urn"], f"whatsapp:{self.phone_number}")
        self.assertEqual(call_args["channel_uuid"], str(self.channel_uuid))
        self.assertIn("order_form_id", call_args["payload"])
        self.assertIn("value", call_args["payload"])
        self.assertIn("currency", call_args["payload"])

    def test_execute_uses_cart_phone_as_fallback(self):
        """Test that cart phone is used when order has no phone."""
        order_details_no_phone = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {},
            "storePreferencesData": {"currencyCode": "BRL"},
            "value": 10000,
            "creationDate": (
                self.notification_sent_at + timezone.timedelta(hours=1)
            ).isoformat(),
        }

        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )
        self.mock_flows_service.send_purchase_event.return_value = self.mock_response

        usecase = self._create_usecase()
        context = self._create_context(order_details=order_details_no_phone)

        result = usecase.execute(context)

        self.assertTrue(result)
        call_args = self.mock_flows_service.send_purchase_event.call_args[0][0]
        self.assertEqual(call_args["contact_urn"], f"whatsapp:{self.phone_number}")

    def test_init_with_default_services(self):
        """Test initialization with default services."""
        usecase = HandleAbandonedCartConversionUseCase()

        self.assertIsInstance(usecase.flows_service, FlowsService)
        self.assertIsInstance(usecase.cart_repository, CartRepository)
