"""
Use case for handling abandoned cart conversions.

This use case is triggered when a VTEX order is confirmed (payment-approved)
and checks if the order corresponds to a cart that received an abandonment
notification. If so, it sends the conversion event to Flows for datalake storage.
"""

import logging
from typing import Optional, TYPE_CHECKING

from dateutil import parser as date_parser
from django.utils import timezone

from retail.projects.models import Project
from retail.services.flows.service import FlowsService
from retail.vtex.repositories.cart_repository import CartRepository
from retail.vtex.models import Cart
from retail.vtex.usecases.phone_number_normalizer import PhoneNumberNormalizer
from retail.jwt_keys.usecases.generate_jwt import JWTUsecase

if TYPE_CHECKING:
    from retail.vtex.usecases.handle_payment_approved import OrderContext


logger = logging.getLogger(__name__)


class HandleAbandonedCartConversionUseCase:
    """
    Detects and reports conversions from abandoned cart notifications.

    A conversion is detected when:
    1. A VTEX order is confirmed (payment-approved)
    2. The order's order_form_id matches a cart with notification_sent_at set
    3. The order creation date is after the notification was sent
    """

    def __init__(
        self,
        flows_service: Optional[FlowsService] = None,
        cart_repository: Optional[CartRepository] = None,
        jwt_generator: Optional[JWTUsecase] = None,
    ) -> None:
        self.flows_service = flows_service or FlowsService()
        self.cart_repository = cart_repository or CartRepository()
        self.jwt_generator = jwt_generator or JWTUsecase()

    def execute(self, context: "OrderContext") -> bool:
        """Execute the abandoned cart conversion workflow."""
        return self._process_conversion(
            context.project, context.order_details, context.order_form_id
        )

    def _process_conversion(
        self, project: Project, order_details: dict, order_form_id: str
    ) -> bool:
        """Process conversion for a single order."""
        log_prefix = f"[CONVERSION] order_form={order_form_id}"

        cart = self.cart_repository.find_abandoned_cart_for_conversion(
            order_form_id, project
        )
        if not cart:
            logger.debug(f"{log_prefix} No eligible cart")
            return False

        if not self._is_valid_conversion(cart, order_details):
            logger.info(
                f"{log_prefix} Cart {cart.uuid} order placed before notification"
            )
            return False

        payload = self._build_conversion_payload(cart, order_details, order_form_id)
        if not payload:
            return False

        if self._send_to_flows(payload, cart):
            logger.info(
                f"{log_prefix} Conversion sent to datalake for cart {cart.uuid}"
            )
            self.cart_repository.update_capi_notification_sent(cart)
            return True

        logger.error(f"{log_prefix} Failed to send conversion to datalake")
        return False

    def _is_valid_conversion(self, cart: Cart, order_details: dict) -> bool:
        """
        Validate that the order was created after the notification was sent.
        """
        order_creation_date_str = order_details.get("creationDate")
        if not order_creation_date_str:
            logger.warning(f"Order has no creationDate for cart {cart.uuid}")
            return False

        try:
            order_creation_date = date_parser.isoparse(order_creation_date_str)
            notification_sent_date = cart.notification_sent_at

            if timezone.is_naive(notification_sent_date):
                notification_sent_date = timezone.make_aware(notification_sent_date)

            is_valid = order_creation_date > notification_sent_date

            logger.info(
                f"Conversion timing: cart={cart.uuid} "
                f"notification_sent={notification_sent_date} "
                f"order_created={order_creation_date} valid={is_valid}"
            )
            return is_valid

        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing order creation date: {e}")
            return False

    def _build_conversion_payload(
        self, cart: Cart, order_details: dict, order_form_id: str
    ) -> Optional[dict]:
        """Build the payload to send to Flows."""
        phone = self._extract_phone(order_details, cart)
        if not phone:
            logger.warning(f"No phone found for cart {cart.uuid}")
            return None

        channel_uuid = self._extract_channel_uuid(cart)
        if not channel_uuid:
            vtex_account = cart.project.vtex_account if cart.project else "unknown"
            logger.warning(
                f"No channel_uuid found for cart {cart.uuid} vtex_account={vtex_account}"
            )
            return None

        currency = (
            order_details.get("storePreferencesData", {}).get("currencyCode") or "BRL"
        )
        value = round(order_details.get("value", 0) / 100, 2)

        return {
            "event_type": "abandoned_cart_conversion",
            "contact_urn": f"whatsapp:{phone}",
            "channel_uuid": channel_uuid,
            "payload": {
                "order_form_id": order_form_id,
                "value": value,
                "currency": currency,
            },
        }

    def _extract_channel_uuid(self, cart: Cart) -> Optional[str]:
        """Extract channel_uuid from integrated_agent."""
        if cart.integrated_agent and cart.integrated_agent.channel_uuid:
            return str(cart.integrated_agent.channel_uuid)
        return None

    def _extract_phone(self, order_details: dict, cart: Cart) -> Optional[str]:
        """Extract phone from order details or fallback to cart."""
        raw_phone = order_details.get("clientProfileData", {}).get("phone")
        if raw_phone:
            return PhoneNumberNormalizer.normalize(raw_phone)
        return cart.phone_number

    def _send_to_flows(self, payload: dict, cart: Cart) -> bool:
        """Send the conversion event to Flows."""
        try:
            jwt_token = self.jwt_generator.generate_jwt_token(str(cart.project.uuid))
            response = self.flows_service.send_purchase_event(payload, jwt_token)

            if response.status_code != 200:
                logger.error(
                    f"Failed to send conversion. Status: {response.status_code}"
                )
                return False

            logger.info(f"Conversion sent to Flows for cart {cart.uuid}")
            return True

        except Exception as e:
            logger.error(f"Error sending conversion to Flows: {e}")
            return False
