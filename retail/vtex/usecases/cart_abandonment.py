import logging

from retail.clients.vtex_io.client import VtexIOClient
from retail.clients.vtex.client import VtexClient
from retail.services.vtex.service import VtexService
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.models import Cart
from retail.services.code_actions.service import CodeActionsService
from retail.clients.code_actions.client import CodeActionsClient
from retail.clients.exceptions import CustomAPIException
from retail.vtex.usecases.base import BaseVtexUseCase


logger = logging.getLogger(__name__)


class CartAbandonmentUseCase(BaseVtexUseCase):
    """
    Use case for handling cart abandonment and notifications.
    """

    utm_source = "weniabandonedcart"

    def __init__(
        self,
        code_actions_service: CodeActionsService = None,
        vtex_io_service: VtexIOService = None,
        vtex_service: VtexService = None,
        message_builder=None,
    ):
        """
        Initialize dependencies for the CartAbandonmentUseCase.

        Args:
            flows_service (FlowsService): Service to handle notification flows.
            vtex_io_service (VtexIOService): Service for interacting with VtexIO.
            vtex_service (VtexService): Service for interacting with VTEX.
            message_builder (MessageBuilder): Builder for constructing notification messages.
        """
        self.code_actions_service = code_actions_service or CodeActionsService(
            CodeActionsClient()
        )
        self.vtex_io_service = vtex_io_service or VtexIOService(VtexIOClient())
        self.vtex_service = vtex_service or VtexService(VtexClient())

        self.message_builder = message_builder or MessageBuilder()

    def process_abandoned_cart(self, cart_uuid: str):
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
            client_profile = self._extract_client_profile_and_save_locale(
                cart, order_form
            )

            if not order_form.get("items", []):
                # Mark cart as empty if no items are found
                self._update_cart_status(cart, "empty")
                return

            # Check orders by email
            orders = self._fetch_orders_by_email(cart, client_profile["email"])
            self._evaluate_orders(cart, orders, order_form, client_profile)

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

        order_form = self.vtex_io_service.get_order_form_details(
            account_domain=self._get_account_domain(str(cart.project.uuid)),
            order_form_id=cart.order_form_id,
        )
        if not order_form:
            logger.warning(
                f"Order form for {cart.project.vtex_account}-{cart.uuid} is empty."
            )
            raise CustomAPIException("Empty order form.")

        return order_form

    def _extract_client_profile_and_save_locale(
        self, cart: Cart, order_form: dict
    ) -> dict:
        """
        Extract client profile data and save locale from order form.

        Args:
            cart (Cart): The cart instance.
            order_form (dict): Order form details.

        Returns:
            dict: client profile data.
        """
        client_profile = order_form.get("clientProfileData", {})

        # Update cart configuration
        cart.config["client_profile"] = client_profile
        cart.config["locale"] = order_form.get("clientPreferencesData", {}).get(
            "locale", "pt-BR"
        )
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
        orders = self.vtex_io_service.get_order_details(
            account_domain=self._get_account_domain(cart), user_email=email
        )
        return orders or {"list": []}

    def _evaluate_orders(
        self, cart: Cart, orders: dict, order_form: dict, client_profile: dict
    ):
        """
        Evaluate orders and determine the status of the cart.

        Args:
            cart (Cart): The cart instance.
            orders (dict): List of orders retrieved.
            order_form (dict): Order form details.
            client_profile (dict): Client profile data.
        """
        if not orders.get("list"):
            self._mark_cart_as_abandoned(cart, order_form, client_profile)
            return

        recent_orders = orders.get("list", [])[:3]
        for order in recent_orders:
            if order.get("orderFormId") == cart.order_form_id:
                self._update_cart_status(cart, "purchased")
                return

        self._mark_cart_as_abandoned(cart, order_form, client_profile)

    def _set_utm_source(self, cart: Cart):
        domain = self._get_account_domain(cart)
        self.vtex_service.set_order_form_marketing_data(
            domain, cart.order_form_id, self.utm_source
        )

    def _mark_cart_as_abandoned(
        self, cart: Cart, order_form: dict, client_profile: dict
    ) -> None:
        """
        Mark a cart as abandoned and send notification.

        This method updates the cart status to 'abandoned', builds the abandonment message,
        sends the notification through the code actions service, and updates the cart status
        based on the delivery result.

        Args:
            cart (Cart): The cart to process.
            order_form (dict): Order form details containing cart items and pricing.
            client_profile (dict): Client profile data with customer information.

        Returns:
            None
        """
        self._update_cart_status(cart, "abandoned")

        # Get both message and extra parameters
        (
            message_payload,
            message_parameters,
        ) = self.message_builder.build_abandonment_message(cart)
        # Build full extra payload
        extra_payload = {
            "order_form": order_form,
            "client_profile": client_profile,
            **message_parameters,  # Include extra message context
        }

        response = self.code_actions_service.run_code_action(
            action_id=self._get_code_action_id_by_cart(cart),
            message_payload=message_payload,
            extra_payload=extra_payload,
        )

        self._update_cart_status(cart, "delivered_success", response)
        # Set marketing data
        self._set_utm_source(cart)

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

    def _get_code_action_id_by_cart(self, cart: Cart) -> str:
        """
        Get the code action ID for the cart based on feature type.

        Args:
            cart (Cart): The cart instance.

        Returns:
            str: The code action ID.

        Raises:
            ValueError: If integrated feature, vtex account or action ID is not found.
        """
        integrated_feature = cart.integrated_feature
        feature_code = integrated_feature.feature.code
        vtex_account = integrated_feature.project.vtex_account

        # Use feature code to create a specific action name
        action_name = f"{vtex_account}_{feature_code}_send_whatsapp_broadcast"

        action_id = integrated_feature.config.get("code_action_registered", {}).get(
            action_name
        )
        if not action_id:
            raise ValueError(f"Action ID not found for action '{action_name}'")

        return action_id


class MessageBuilder:
    """
    Helper to build broadcast message payloads for abandoned cart notifications.
    """

    def build_abandonment_message(self, cart: Cart) -> tuple[dict, dict]:
        """
        Build the message payload and extra parameters for an abandoned cart notification.

        Args:
            cart (Cart): The cart for which to build the message.

        Returns:
            tuple: (message_payload, extra_parameters)
        """
        template_name = self._get_integrated_feature_config_value(
            cart, "abandoned_cart_template"
        )
        channel_uuid = self._get_integrated_feature_config_value(
            cart, "flow_channel_uuid"
        )
        client_name = self._get_cart_config_value(cart, "client_name")
        locale = self._get_cart_config_value(cart, "locale")
        cart_link = f"{cart.order_form_id}/"

        message_payload = {
            "project": str(cart.project.uuid),
            "urns": [f"whatsapp:{cart.phone_number}"],
            "channel": channel_uuid,
            "msg": {
                "template": {
                    "locale": locale,
                    "name": template_name,
                    "variables": [f"{client_name}"],
                },
                "buttons": [
                    {
                        "sub_type": "url",
                        "parameters": [{"type": "text", "text": cart_link}],
                    }
                ],
            },
        }

        # Parameters that may help Code Action logic
        extra_parameters = {
            "project_uuid": str(cart.project.uuid),
            "flow_channel_uuid": channel_uuid,
            "client_name": client_name,
            "locale": locale,
            "cart_link": cart_link,
        }

        return message_payload, extra_parameters

    def _get_integrated_feature_config_value(self, cart: Cart, key: str) -> str:
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
