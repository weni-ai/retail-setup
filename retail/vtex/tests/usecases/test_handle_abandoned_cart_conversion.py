from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.projects.models import Project
from retail.services.flows.service import FlowsService
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.models import Cart
from retail.vtex.repositories.cart_repository import CartRepository
from retail.vtex.usecases.handle_abandoned_cart_conversion import (
    HandleAbandonedCartConversionUseCase,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "handle-abandoned-cart-conversion-tests",
        }
    }
)
class HandleAbandonedCartConversionUseCaseTest(TestCase):
    """Test cases for HandleAbandonedCartConversionUseCase."""

    def setUp(self):
        cache.clear()

        self.order_id = "test_order_123"
        self.order_form_id = "test_order_form_456"
        self.cart_uuid = uuid4()
        self.channel_uuid = uuid4()
        self.phone_number = "5511999999999"
        self.notification_sent_at = timezone.now()

        self.mock_vtex_io_service = MagicMock(spec=VtexIOService)
        self.mock_flows_service = MagicMock(spec=FlowsService)
        self.mock_cart_repository = MagicMock(spec=CartRepository)
        self.mock_jwt_generator = MagicMock()
        self.mock_jwt_generator.generate_jwt_token.return_value = "mock_jwt_token"

        self.project = Project.objects.create(
            name="Conversion Test Project",
            uuid=uuid4(),
            vtex_account="test_account",
        )

        self.mock_integrated_agent = MagicMock(spec=IntegratedAgent)
        self.mock_integrated_agent.channel_uuid = self.channel_uuid

        self.mock_cart = MagicMock(spec=Cart)
        self.mock_cart.uuid = self.cart_uuid
        self.mock_cart.phone_number = self.phone_number
        self.mock_cart.notification_sent_at = self.notification_sent_at
        self.mock_cart.project = self.project
        self.mock_cart.integrated_agent = self.mock_integrated_agent

        self.mock_order_details = {
            "orderFormId": self.order_form_id,
            "clientProfileData": {"phone": self.phone_number},
            "storePreferencesData": {"currencyCode": "BRL"},
            "value": 10000,
            "creationDate": (
                self.notification_sent_at + timedelta(hours=1)
            ).isoformat(),
        }

        self.mock_response = MagicMock()
        self.mock_response.status_code = 200

        self.mock_vtex_io_service.get_order_details_by_id.return_value = (
            self.mock_order_details
        )
        self.mock_flows_service.send_purchase_event.return_value = self.mock_response

    def tearDown(self):
        cache.clear()

    def _create_usecase(self):
        return HandleAbandonedCartConversionUseCase(
            vtex_io_service=self.mock_vtex_io_service,
            flows_service=self.mock_flows_service,
            cart_repository=self.mock_cart_repository,
            jwt_generator=self.mock_jwt_generator,
        )

    def _execute(self, usecase):
        return usecase.execute(
            order_id=self.order_id, project_uuid=str(self.project.uuid)
        )

    def test_execute_successful_conversion(self):
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        result = self._execute(self._create_usecase())

        self.assertTrue(result)
        self.mock_cart_repository.find_abandoned_cart_for_conversion.assert_called_once_with(
            self.order_form_id, self.project
        )
        self.mock_flows_service.send_purchase_event.assert_called_once()
        self.mock_cart_repository.update_capi_notification_sent.assert_called_once_with(
            self.mock_cart
        )

    def test_execute_project_not_found(self):
        result = self._create_usecase().execute(
            order_id=self.order_id, project_uuid=str(uuid4())
        )

        self.assertFalse(result)
        self.mock_vtex_io_service.get_order_details_by_id.assert_not_called()
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_no_order_details(self):
        self.mock_vtex_io_service.get_order_details_by_id.return_value = None

        result = self._execute(self._create_usecase())

        self.assertFalse(result)
        self.mock_cart_repository.find_abandoned_cart_for_conversion.assert_not_called()
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_no_order_form_id(self):
        self.mock_vtex_io_service.get_order_details_by_id.return_value = {
            "value": 10000,
        }

        result = self._execute(self._create_usecase())

        self.assertFalse(result)
        self.mock_cart_repository.find_abandoned_cart_for_conversion.assert_not_called()

    def test_execute_no_eligible_cart(self):
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = None

        result = self._execute(self._create_usecase())

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_order_before_notification(self):
        self.mock_order_details["creationDate"] = (
            self.notification_sent_at - timedelta(hours=1)
        ).isoformat()
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        result = self._execute(self._create_usecase())

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_no_creation_date(self):
        del self.mock_order_details["creationDate"]
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        result = self._execute(self._create_usecase())

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_invalid_creation_date(self):
        self.mock_order_details["creationDate"] = "not-a-date"
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        result = self._execute(self._create_usecase())

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_no_channel_uuid(self):
        cart_no_channel = MagicMock(spec=Cart)
        cart_no_channel.uuid = self.cart_uuid
        cart_no_channel.phone_number = self.phone_number
        cart_no_channel.notification_sent_at = self.notification_sent_at
        cart_no_channel.project = self.project
        cart_no_channel.integrated_agent = None
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            cart_no_channel
        )

        result = self._execute(self._create_usecase())

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_no_phone_returns_false(self):
        self.mock_order_details["clientProfileData"] = {}
        cart_no_phone = MagicMock(spec=Cart)
        cart_no_phone.uuid = self.cart_uuid
        cart_no_phone.phone_number = None
        cart_no_phone.notification_sent_at = self.notification_sent_at
        cart_no_phone.project = self.project
        cart_no_phone.integrated_agent = self.mock_integrated_agent
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            cart_no_phone
        )

        result = self._execute(self._create_usecase())

        self.assertFalse(result)
        self.mock_flows_service.send_purchase_event.assert_not_called()

    def test_execute_uses_cart_phone_as_fallback(self):
        self.mock_order_details["clientProfileData"] = {}
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        result = self._execute(self._create_usecase())

        self.assertTrue(result)
        call_args = self.mock_flows_service.send_purchase_event.call_args[0][0]
        self.assertEqual(call_args["contact_urn"], f"whatsapp:{self.phone_number}")

    def test_execute_flows_service_failure(self):
        failed_response = MagicMock()
        failed_response.status_code = 500
        self.mock_flows_service.send_purchase_event.return_value = failed_response
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        result = self._execute(self._create_usecase())

        self.assertFalse(result)
        self.mock_cart_repository.update_capi_notification_sent.assert_not_called()

    def test_execute_flows_service_raises_does_not_propagate(self):
        self.mock_flows_service.send_purchase_event.side_effect = RuntimeError("boom")
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        result = self._execute(self._create_usecase())

        self.assertFalse(result)

    def test_execute_payload_structure(self):
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        self._execute(self._create_usecase())

        payload = self.mock_flows_service.send_purchase_event.call_args[0][0]
        self.assertEqual(payload["event_type"], "abandoned_cart")
        self.assertEqual(payload["contact_urn"], f"whatsapp:{self.phone_number}")
        self.assertEqual(payload["channel_uuid"], str(self.channel_uuid))
        self.assertEqual(payload["payload"]["order_form_id"], self.order_form_id)
        self.assertEqual(payload["payload"]["value"], 100.00)
        self.assertEqual(payload["payload"]["currency"], "BRL")

    def test_execute_currency_falls_back_to_brl(self):
        self.mock_order_details["storePreferencesData"] = {}
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        self._execute(self._create_usecase())

        payload = self.mock_flows_service.send_purchase_event.call_args[0][0]
        self.assertEqual(payload["payload"]["currency"], "BRL")

    def test_init_with_default_services(self):
        usecase = HandleAbandonedCartConversionUseCase()

        self.assertIsInstance(usecase.flows_service, FlowsService)
        self.assertIsInstance(usecase.cart_repository, CartRepository)
        self.assertIsInstance(usecase.vtex_io_service, VtexIOService)

    def test_execute_uses_cached_project(self):
        """Cache hit short-circuits the DB lookup and still proceeds."""
        cache.set(f"project_by_uuid_{self.project.uuid}", self.project, timeout=60)
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        with patch(
            "retail.vtex.usecases.handle_abandoned_cart_conversion.Project.objects.get"
        ) as mock_get:
            result = self._execute(self._create_usecase())
            mock_get.assert_not_called()

        self.assertTrue(result)

    def test_execute_handles_multiple_projects_returned(self):
        """``Project.MultipleObjectsReturned`` aborts the workflow gracefully."""
        with patch(
            "retail.vtex.usecases.handle_abandoned_cart_conversion.Project.objects.get",
            side_effect=Project.MultipleObjectsReturned,
        ):
            result = self._create_usecase().execute(
                order_id=self.order_id, project_uuid=str(uuid4())
            )

        self.assertFalse(result)
        self.mock_vtex_io_service.get_order_details_by_id.assert_not_called()

    def test_execute_handles_vtex_io_exception(self):
        """Exceptions raised by VTEX I/O are caught and treated as no order."""
        self.mock_vtex_io_service.get_order_details_by_id.side_effect = RuntimeError(
            "vtex-io-down"
        )

        result = self._execute(self._create_usecase())

        self.assertFalse(result)
        self.mock_cart_repository.find_abandoned_cart_for_conversion.assert_not_called()

    def test_execute_makes_naive_notification_sent_at_aware(self):
        """Naive ``notification_sent_at`` values are coerced to aware before
        being compared against the order ``creationDate``.
        """
        from datetime import datetime

        naive_notification = datetime(2026, 5, 1, 10, 0, 0)
        self.mock_cart.notification_sent_at = naive_notification
        self.mock_order_details["creationDate"] = (
            timezone.make_aware(naive_notification) + timedelta(hours=1)
        ).isoformat()
        self.mock_cart_repository.find_abandoned_cart_for_conversion.return_value = (
            self.mock_cart
        )

        result = self._execute(self._create_usecase())

        self.assertTrue(result)
        self.mock_flows_service.send_purchase_event.assert_called_once()
