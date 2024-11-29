import logging

from django.conf import settings

from retail.vtex.models import Cart
from retail.services.flows.service import FlowsService
from retail.clients.flows.client import FlowsClient
from retail.clients.exceptions import CustomAPIException


logger = logging.getLogger(__name__)


class CartAbandonmentUseCase:
    """
    Use case for handling cart abandonment and notifications.
    """

    def __init__(self):
        self.flows_service = FlowsService(FlowsClient())
        self.message_builder = MessageBuilder()

    def process_abandoned_cart(self, cart_uuid: str):
        """
        Process a cart marked as abandoned.

        Args:
            cart_uuid (str): The UUID of the cart to process.
        """
        try:
            # Fetch the cart
            cart = Cart.objects.get(uuid=cart_uuid, status="created")
            self._mark_cart_as_abandoned(cart)

            # Prepare and send the notification
            payload = self.message_builder.build_abandonment_message(cart)
            response = self.flows_service.send_whatsapp_broadcast(
                payload=payload,
                project_uuid=cart.project.uuid,
                user_email=settings.FLOWS_USER_CRM_EMAIL,
            )
            # Update cart status based on the response
            self._update_cart_status(cart, "delivered_success", response)
        except Cart.DoesNotExist:
            logger.warning(
                f"Cart with UUID {cart_uuid} does not exist or is already processed."
            )
        except CustomAPIException as e:
            logger.error(
                f"Unexpected error while processing cart {cart_uuid}: {str(e)}"
            )
            self._handle_error(cart_uuid, str(e))

    def _mark_cart_as_abandoned(self, cart: Cart):
        """
        Mark a cart as abandoned.

        Args:
            cart (Cart): The cart to mark as abandoned.
        """
        cart.abandoned = True
        cart.save()

    def _send_broadcast(self, cart: Cart, msg_payload: dict, token: str) -> dict:
        """
        Send a broadcast notification for the abandoned cart.

        Args:
            cart (Cart): The cart for which to send the notification.
            msg_payload (dict): The message payload.
            token (str): The API token for authentication.

        Returns:
            dict: The response from the broadcast service.
        """
        phone_number = f"tel:{cart.phone_number}"
        return self.flows_service.send_whatsapp_broadcast(
            urns=[phone_number],
            text="Cart abandoned notification",
            msg=msg_payload,
            token=token,
        )

    def _update_cart_status(self, cart: Cart, status: str, response=None):
        """
        Update the cart's status and log errors if applicable.

        Args:
            cart (Cart): The cart to update.
            status (str): The new status to set.
            response (dict, optional): The response from the broadcast service. Defaults to None.
        """
        cart.status = status
        if status == "delivered_error" and response:
            cart.error_message = f"Broadcast failed: {response}"
        cart.save()

    def _handle_error(self, cart_uuid: str, error_message: str):
        """
        Handle unexpected errors by logging them to the cart.

        Args:
            cart_uuid (str): The UUID of the cart.
            error_message (str): The error message to log.
        """
        try:
            cart = Cart.objects.get(uuid=cart_uuid)
            self._update_cart_status(cart, "delivered_error", error_message)
        except Cart.DoesNotExist:
            logger.error(f"Cart not found during error handling: {error_message}")


class MessageBuilder:
    """
    Helper to build broadcast message payloads for abandoned cart notifications.
    """

    def build_abandonment_message(self, cart: Cart) -> dict:
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
        cart_link = self._get_cart_config_value(cart, "cart_url")

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
