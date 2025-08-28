import logging

from typing import Optional

from django.core.cache import cache

from retail.projects.models import Project
from retail.services.flows.service import FlowsService
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.repositories.cart_repository import CartRepository
from retail.vtex.models import Cart

from retail.vtex.usecases.phone_number_normalizer import PhoneNumberNormalizer


logger = logging.getLogger(__name__)


class HandlePurchaseEventUseCase:
    """
    Use case responsible for orchestrating the confirmation of a purchase event
    and sending the notification to the Flows system.

    This use case:
      - Fetches the project and validates its existence.
      - Queries VTEX for order details.
      - Checks for an associated cart with the given order_form_id.
      - Constructs the payload and invokes the Flows client.
    """

    def __init__(
        self,
        vtex_io_service: Optional[VtexIOService] = None,
        flows_service: Optional[FlowsService] = None,
        cart_repository: Optional[CartRepository] = None,
    ) -> None:
        """
        Initializes the use case with its dependencies.

        Args:
            order_service: Service to query VTEX for order details.
            flows_client: Client to send events to Flows.
            cart_repository: Repository to fetch Cart entities.
        """
        self.vtex_io_service = vtex_io_service or VtexIOService()
        self.flows_service = flows_service or FlowsService()
        self.cart_repository = cart_repository or CartRepository()

    def execute(self, order_id: str, project_uuid: str) -> None:
        """
        Executes the purchase event workflow.

        Args:
            order_id: The VTEX order ID to process.
            project_uuid: The UUID of the project to which the order belongs.

        Returns:
            None
        """
        project = self._get_project(project_uuid)
        if not project:
            logger.error(f"Project with UUID '{project_uuid}' not found.")
            return

        order_details = self._get_order_details(order_id, project)
        if not order_details:
            logger.info(f"Order '{order_id}' not found in VTEX.")
            return

        order_form_id = self._extract_order_form_id(order_details)
        if not order_form_id:
            logger.info(f"No order_form_id found for order '{order_id}'.")
            return

        cart = self._get_cart(order_form_id, project)
        if not cart:
            logger.info(
                f"No cart found for order_form_id '{order_form_id}' and project '{project.uuid}'."
            )
            return

        if cart.status == "purchased":
            logger.info(
                f"Cart {cart.uuid} already marked as 'purchased'. "
                "Skipping Flows event to prevent duplicate notification."
            )
            return

        logger.info(f"Marking cart {cart.uuid} as purchased on purchase event.")
        self.cart_repository.update_status(cart, "purchased")

        logger.info(f"Building purchase event payload for cart {cart.uuid}.")
        payload = self._build_purchase_event_payload(
            cart=cart,
            order_details=order_details,
            order_form_id=order_form_id,
        )

        logger.info(f"Sending purchase event payload to Flows for cart {cart.uuid}.")
        self._send_to_flows(payload)

    def _get_project(self, project_uuid: str) -> Optional[Project]:
        """
        Fetches the project by its UUID, using cache for performance.

        Args:
            project_uuid: The UUID of the project.

        Returns:
            The corresponding Project instance or None if not found.
        """
        cache_key = f"project_by_uuid_{project_uuid}"
        project = cache.get(cache_key)

        if project:
            return project

        try:
            project = Project.objects.get(uuid=project_uuid)
            cache.set(cache_key, project, timeout=43200)  # 12 hours
            return project
        except Project.DoesNotExist:
            logger.info(f"Project not found for UUID {project_uuid}.")
            return None
        except Project.MultipleObjectsReturned:
            logger.error(
                f"Multiple projects found for UUID {project_uuid}.",
                exc_info=True,
            )
            return None

    def _get_order_details(self, order_id: str, project: Project) -> Optional[dict]:
        """
        Retrieves order details from VTEX.

        Args:
            order_id: The VTEX order ID.
            project: The project entity, providing the VTEX account context.

        Returns:
            A dictionary containing the order details, or None if not found.
        """
        account_domain = f"{project.vtex_account}.myvtex.com"
        return self.vtex_io_service.get_order_details_by_id(account_domain, order_id)

    def _extract_order_form_id(self, order_details: dict) -> Optional[str]:
        """
        Extracts the order_form_id from the VTEX order details.

        Args:
            order_details: The dictionary returned by VTEX order API.

        Returns:
            The order_form_id as a string, or None if not present.
        """
        return order_details.get("orderFormId")

    def _get_cart(self, order_form_id: str, project: Project) -> Optional[Cart]:
        """
        Retrieves the cart entity associated with the given order_form_id and project.

        Args:
            order_form_id: The order form identifier from VTEX.
            project: The project entity.

        Returns:
            The Cart entity or None if not found.
        """
        return self.cart_repository.find_by_order_form(order_form_id, project)

    def _build_purchase_event_payload(
        self, cart: Cart, order_details: dict, order_form_id: str
    ) -> dict:
        """
        Constructs the payload to be sent to the Flows system.

        Args:
            cart: The Cart entity containing customer information.
            order_details: The VTEX order details dictionary.
            order_form_id: The VTEX order form ID.

        Returns:
            A dictionary ready to be posted to the Flows endpoint.
        """

        flows_channel_uuid = str(cart.flows_channel_uuid)

        # Extract and normalize phone
        raw_phone = order_details.get("clientProfileData", {}).get("phone")
        phone = PhoneNumberNormalizer.normalize(raw_phone) if raw_phone else None

        # Extract currency
        currency = (
            order_details.get("storePreferencesData", {}).get("currencyCode") or "BRL"
        )

        # Extract value (in cents, must divide by 100)
        value_cents = order_details.get("value", 0)
        value = round(value_cents / 100, 2)

        if not phone:
            logger.warning(f"No phone number found for order form {order_form_id}.")
            return

        return {
            "event_type": "purchase",
            "contact_urn": f"whatsapp:{phone}",
            "channel_uuid": flows_channel_uuid,
            "payload": {
                "order_form_id": order_form_id,
                "value": value,
                "currency": currency,
            },
        }

    def _send_to_flows(self, payload: dict) -> bool:
        """
        Sends the constructed event payload to the Flows system.

        Args:
            payload: The purchase event data to send.

        Returns:
            True if the request was successful, False otherwise.
        """
        response = self.flows_service.send_purchase_event(payload)

        if response.status_code == 200:
            logger.info(
                f"Successfully sent purchase event to Flows. " f"Payload: {payload}"
            )
            return True
        else:
            logger.error(
                f"Failed to send purchase event to Flows. "
                f"Payload: {payload} | Status: {response.status_code}"
            )
            return False
