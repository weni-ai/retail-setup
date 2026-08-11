"""
Use case for handling abandoned cart conversions.

Triggered when a VTEX order reaches ``payment-approved``. If the matching
``order_form_id`` corresponds to a cart that previously received an
abandonment notification (``notification_sent_at`` populated), the conversion
is reported to Flows so it can be persisted in the analytics datalake.
"""

import logging

from typing import Optional

from dateutil import parser as date_parser
from django.core.cache import cache
from django.utils import timezone

from retail.jwt_keys.usecases.generate_jwt import JWTUsecase
from retail.projects.models import Project
from retail.services.flows.service import FlowsService
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.models import Cart
from retail.vtex.repositories.cart_repository import CartRepository
from retail.vtex.usecases.phone_number_normalizer import PhoneNumberNormalizer


logger = logging.getLogger(__name__)


class HandleAbandonedCartConversionUseCase:
    """
    Detect and report conversions originated from abandoned-cart notifications.

    A conversion is detected when:
      1. A VTEX order reaches ``payment-approved``.
      2. The order ``orderFormId`` matches a Cart with
         ``notification_sent_at`` populated and ``capi_notification_sent=False``.
      3. The order ``creationDate`` is later than the notification timestamp,
         which guarantees the order really followed the notification rather
         than predating it.
    """

    def __init__(
        self,
        vtex_io_service: Optional[VtexIOService] = None,
        flows_service: Optional[FlowsService] = None,
        cart_repository: Optional[CartRepository] = None,
        jwt_generator: Optional[JWTUsecase] = None,
    ) -> None:
        self.vtex_io_service = vtex_io_service or VtexIOService()
        self.flows_service = flows_service or FlowsService()
        self.cart_repository = cart_repository or CartRepository()
        self.jwt_generator = jwt_generator or JWTUsecase()

    def execute(self, order_id: str, project_uuid: str) -> bool:
        """Run the abandoned-cart conversion workflow for a single order."""
        log_prefix = (
            f"[ABANDONED_CART_CONVERSION] order_id={order_id} project={project_uuid}"
        )

        project = self._get_project(project_uuid)
        if not project:
            logger.debug(f"{log_prefix} Project not found")
            return False

        order_details = self._get_order_details(order_id, project)
        if not order_details:
            logger.debug(f"{log_prefix} Order details not found in VTEX")
            return False

        order_form_id = order_details.get("orderFormId")
        if not order_form_id:
            logger.debug(f"{log_prefix} No order_form_id in order details")
            return False

        return self._process_conversion(project, order_details, order_form_id)

    def _process_conversion(
        self, project: Project, order_details: dict, order_form_id: str
    ) -> bool:
        log_prefix = f"[ABANDONED_CART_CONVERSION] order_form={order_form_id}"

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
        """Validate that the order was created after the notification was sent."""
        order_creation_date_str = order_details.get("creationDate")
        if not order_creation_date_str:
            logger.warning(f"Order has no creationDate for cart {cart.uuid}")
            return False

        try:
            order_creation_date = date_parser.isoparse(order_creation_date_str)
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing order creation date: {e}")
            return False

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

    def _build_conversion_payload(
        self, cart: Cart, order_details: dict, order_form_id: str
    ) -> Optional[dict]:
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
            "event_type": "abandoned_cart",
            "contact_urn": f"whatsapp:{phone}",
            "channel_uuid": channel_uuid,
            "payload": {
                "order_form_id": order_form_id,
                "value": value,
                "currency": currency,
            },
        }

    def _extract_channel_uuid(self, cart: Cart) -> Optional[str]:
        if cart.integrated_agent and cart.integrated_agent.channel_uuid:
            return str(cart.integrated_agent.channel_uuid)
        return None

    def _extract_phone(self, order_details: dict, cart: Cart) -> Optional[str]:
        raw_phone = order_details.get("clientProfileData", {}).get("phone")
        if raw_phone:
            return PhoneNumberNormalizer.normalize(raw_phone)
        return cart.phone_number

    def _send_to_flows(self, payload: dict, cart: Cart) -> bool:
        try:
            jwt_token = self.jwt_generator.generate_jwt_token(str(cart.project.uuid))
            response = self.flows_service.send_purchase_event(payload, jwt_token)
        except Exception as e:
            logger.error(f"Error sending conversion to Flows: {e}")
            return False

        if response.status_code != 200:
            logger.error(f"Failed to send conversion. Status: {response.status_code}")
            return False

        logger.info(f"Conversion sent to Flows for cart {cart.uuid}")
        return True

    def _get_project(self, project_uuid: str) -> Optional[Project]:
        """Fetch the project by UUID, using cache for performance."""
        cache_key = f"project_by_uuid_{project_uuid}"
        project = cache.get(cache_key)
        if project:
            return project

        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            return None
        except Project.MultipleObjectsReturned:
            logger.error(f"Multiple projects found for UUID {project_uuid}")
            return None

        cache.set(cache_key, project, timeout=43200)
        return project

    def _get_order_details(self, order_id: str, project: Project) -> Optional[dict]:
        account_domain = f"{project.vtex_account}.myvtex.com"
        try:
            return self.vtex_io_service.get_order_details_by_id(
                account_domain=account_domain,
                project_uuid=str(project.uuid),
                order_id=order_id,
            )
        except Exception as e:
            logger.error(f"Error fetching order details: {e}")
            return None
