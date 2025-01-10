import logging

from django.conf import settings

from retail.clients.vtex_io.client import VtexIOClient
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.models import Cart
from retail.services.flows.service import FlowsService
from retail.clients.flows.client import FlowsClient
from retail.clients.exceptions import CustomAPIException
from retail.vtex.usecases.phone_number_normalizer import PhoneNumberNormalizer


logger = logging.getLogger(__name__)


class CartAbandonmentUseCase:
    """
    Use case for handling cart abandonment and notifications.
    """

    def __init__(
        self,
        flows_service: FlowsService = None,
        vtex_client: VtexIOService = None,
        message_builder=None,
    ):
        """
        Initialize dependencies for the CartAbandonmentUseCase.

        Args:
            flows_service (FlowsService): Service to handle notification flows.
            vtex_client (VtexIOService): Client for interacting with VTEX API.
            message_builder (MessageBuilder): Builder for constructing notification messages.
        """
        self.flows_service = flows_service or FlowsService(FlowsClient())
        self.vtex_client = vtex_client or VtexIOService(VtexIOClient())
        self.message_builder = message_builder or MessageBuilder()

    def process_abandoned_cart(self, cart_uuid: str, store: str):
        """
        Process a cart marked as abandoned.

        Args:
            cart_uuid (str): The UUID of the cart to process.
        """
        try:
            # Fetch the cart
            cart = self._get_cart(cart_uuid)

            # Fetch order form details from VTEX IO
            order_form = self._fetch_order_form(cart)

            # Process and update cart information
            client_profile = self._extract_client_profile(cart, order_form)

            if not order_form.get("items", []):
                # Mark cart as empty if no items are found
                self._update_cart_status(cart, "empty")
                return

            # Check orders by email
            orders = self._fetch_orders_by_email(cart, client_profile["email"])
            self._evaluate_orders(cart, orders, store, order_form)

        except Cart.DoesNotExist:
            logger.warning(
                f"Cart with UUID {cart_uuid} does not exist or is already processed."
            )
        except CustomAPIException as e:
            logger.error(
                f"Unexpected error while processing cart {cart_uuid}: {str(e)}"
            )
            self._handle_error(cart_uuid, str(e))

    def _get_cart(self, cart_uuid: str) -> Cart:
        """
        Retrieve the cart instance by UUID.

        Args:
            cart_uuid (str): The UUID of the cart.

        Returns:
            Cart: The cart instance.

        Raises:
            Cart.DoesNotExist: If no cart is found with the given UUID.
        """
        return Cart.objects.get(uuid=cart_uuid, status="created")

    def _fetch_order_form(self, cart: Cart) -> dict:
        """
        Retrieve order form details from VTEX API.

        Args:
            cart (Cart): The cart instance.

        Returns:
            dict: The order form details.

        Raises:
            CustomAPIException: If the API request fails.
        """

        order_form = self.vtex_client.get_order_form_details(
            account_domain=self._get_account_domain(cart), order_form_id=cart.cart_id
        )
        if not order_form:
            logger.warning(
                f"Order form for {cart.project.vtex_account}-{cart.uuid} is empty."
            )
            raise CustomAPIException("Empty order form.")

        return order_form

    def _extract_client_profile(self, cart: Cart, order_form: dict) -> dict:
        """
        Extract and normalize client profile data from order form.

        Args:
            cart (Cart): The cart instance.
            order_form (dict): Order form details.

        Returns:
            dict: Normalized client profile data.
        """
        client_profile = order_form.get("clientProfileData", {})

        # Update cart configuration and phone number
        cart.config["client_profile"] = client_profile
        cart.save()

        return client_profile

    def _fetch_orders_by_email(self, cart: Cart, email: str) -> dict:
        """
        Fetch orders associated with a given email.

        Args:
            cart (Cart): The cart instance.
            email (str): The client email address.

        Returns:
            dict: List of orders associated with the email.
        """
        orders = self.vtex_client.get_order_details(
            account_domain=self._get_account_domain(cart), user_email=email
        )
        return orders or {"list": []}

    def _evaluate_orders(self, cart: Cart, orders: dict, store: str, order_form: dict):
        """
        Evaluate orders and determine the status of the cart.

        Args:
            cart (Cart): The cart instance.
            orders (dict): List of orders retrieved.
        """
        if not orders.get("list"):
            self._mark_cart_as_abandoned(cart, store, {"list": []})
            return

        recent_orders = orders.get("list", [])[:3]
        for order in recent_orders:
            if order.get("orderFormId") == cart.cart_id:
                self._update_cart_status(cart, "purchased")
                return

        self._mark_cart_as_abandoned(cart, store, order_form)

    def _mark_cart_as_abandoned(self, cart: Cart, store, order_form):
        """
        Mark a cart as abandoned and send notification.

        Args:
            cart (Cart): The cart to process.
        """
        self._update_cart_status(cart, "abandoned")

        # Prepare and send the notification
        payload = self.message_builder.build_abandonment_message(cart, store, order_form)
        response = self.flows_service.send_whatsapp_broadcast(
            payload=payload,
            project_uuid=cart.project.uuid,
            user_email=settings.FLOWS_USER_CRM_EMAIL,
        )
        self._update_cart_status(cart, "delivered_success", response)

    def _update_cart_status(self, cart: Cart, status: str, response=None):
        """
        Update the cart's status and log errors if applicable.

        Args:
            cart (Cart): The cart to update.
            status (str): The new status to set.
            response (dict, optional): The response from the broadcast service.
        """
        cart.status = status
        if status == "delivered_error" and response:
            cart.error_message = f"Broadcast failed: {response}"
        cart.save()

    def _handle_error(self, cart_uuid: str, error_message: str):
        """
        Handle errors by logging and updating the cart status.

        Args:
            cart_uuid (str): The UUID of the cart.
            error_message (str): Error message to log.
        """
        try:
            cart = Cart.objects.get(uuid=cart_uuid)
            self._update_cart_status(cart, "delivered_error", error_message)
        except Cart.DoesNotExist:
            logger.error(f"Cart not found during error handling: {error_message}")

    def _get_account_domain(self, cart: Cart) -> str:
        return f"dev5--{cart.project.vtex_account}.myvtex.com"


class MessageBuilder:
    """
    Helper to build broadcast message payloads for abandoned cart notifications.
    """

    def build_abandonment_message(self, cart: Cart, store: str, order_form) -> dict:
        """
        Build the message payload for an abandoned cart notification.

        Args:
            cart (Cart): The cart for which to build the message.

        Returns:
            dict: The message payload.

        Raises:
            ValueError: If required data is missing in the cart or feature.
        """
        # Fetch required data from the cart's integrated feature
        template_uuid = self._get_feature_config_value(cart, "template_message")
        channel_uuid = self._get_feature_config_value(cart, "flow_channel_uuid")

        # Fetch cart-specific data
        cart_link = self._get_cart_link(order_form, store)

        # Build the payload
        return {
            "urns": [f"whatsapp:{cart.phone_number}"],
            "channel": channel_uuid,
            "msg": {
                "template": {
                    "uuid": template_uuid,
                    "variables": ["@contact.name"],
                },
                "buttons": [
                    {
                        "sub_type": "url",
                        "parameters": [{"type": "text", "text": cart_link}],
                    }
                ],
            },
        }

    def _get_feature_config_value(self, cart: Cart, key: str) -> str:
        """
        Helper method to retrieve a configuration value from the integrated feature.

        Args:
            cart (Cart): The cart containing the integrated feature.
            key (str): The key to fetch from the feature's configuration.

        Returns:
            str: The value associated with the key.

        Raises:
            ValueError: If the key is missing.
        """
        value = cart.integrated_feature.config.get(key)
        if not value:
            raise ValueError(
                f"Failed to retrieve '{key}' from feature '{cart.integrated_feature.feature.name}'."
            )
        return value

    def _get_cart_config_value(self, cart: Cart, key: str) -> str:
        """
        Helper method to retrieve a configuration value from the cart.

        Args:
            cart (Cart): The cart to fetch the value from.
            key (str): The key to fetch from the cart's configuration.

        Returns:
            str: The value associated with the key.

        Raises:
            ValueError: If the key is missing.
        """
        value = cart.config.get(key)
        if not value:
            raise ValueError(f"Failed to retrieve '{key}' from the cart configuration.")
        return value
    
    def _get_cart_link(self, order_form: dict, store: str):
        cart_link = store + "/checkout/cart/add?sc=1"
        for item in order_form.get("items"):
            cart_link += f"&sku={item.get('productId')}&qty={item.get('quantity')}&seller={item.get('seller')}"
        return cart_link
