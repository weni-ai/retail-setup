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
from datetime import timedelta
from django.utils import timezone
from django.conf import settings

from retail.webhooks.vtex.utils import PhoneNotificationLockService

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
        notification_lock_service: PhoneNotificationLockService = None,
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
        self.notification_lock_service = (
            notification_lock_service or PhoneNotificationLockService()
        )

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
                # Check if this project should ignore empty cart validation
                project_uuid = str(cart.project.uuid)
                ignore_empty_carts_projects = getattr(
                    settings, "IGNORE_EMPTY_CARTS_FOR_PROJECTS", []
                )

                if project_uuid in ignore_empty_carts_projects:
                    logger.info(
                        f"Cart {cart_uuid} is empty but project {project_uuid} "
                        f"(VTEX: {cart.project.vtex_account}) is configured to ignore empty carts - "
                        "continuing processing"
                    )
                    # Continue processing instead of marking as empty
                else:
                    # Mark cart as empty if no items are found (original behavior)
                    self._update_cart_status(cart, "empty")
                    logger.info(
                        f"Cart {cart_uuid} is empty - marking as empty (VTEX: {cart.project.vtex_account})"
                    )
                    return

            # Save cart items
            self._save_cart_items(cart, order_form)

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

    def _save_cart_items(self, cart: Cart, order_form: dict):
        """
        Save cart items to the cart.
        """
        cart.config["cart_items"] = order_form.get("items", [])
        cart.save()

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
            account_domain=self._get_account_domain(str(cart.project.uuid)),
            user_email=email,
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
            logger.info(
                f"Cart {cart.uuid} orders is empty - marking as abandoned to {cart.phone_number}"
            )
            return

        recent_orders = orders.get("list", [])[:5]

        if self._check_recent_purchases_for_cart_items(cart, recent_orders):
            logger.info(
                f"Cart {cart.uuid} items already purchased recently - marking as purchased to {cart.phone_number}"
            )
            self._update_cart_status(cart, "purchased")
            return

        self._mark_cart_as_abandoned(cart, order_form, client_profile)

    def _set_utm_source(self, cart: Cart):
        domain = self._get_account_domain(str(cart.project.uuid))
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
        # Check if abandoned cart notification cooldown is configured and should be applied
        if self._check_abandoned_cart_notification_cooldown(cart):
            logger.info(
                f"Skipping notification for cart {cart.uuid} - abandoned cart notification cooldown active"
            )
            self._update_cart_status(cart, "skipped_abandoned_cart_cooldown")
            return

        # Check if identical cart was already sent recently
        if self._check_identical_cart_sent_recently(cart):
            logger.info(
                f"Skipping notification for cart {cart.uuid} - identical cart already sent recently"
            )
            self._update_cart_status(cart, "skipped_identical_cart")
            return

        # Acquire lock to prevent multiple notifications for the same phone number
        if not self.notification_lock_service.acquire_lock(
            cart.phone_number, cart.uuid
        ):
            logger.info(
                f"Skipping notification for cart {cart.uuid} - "
                f"notification already in progress for phone {cart.phone_number}"
            )
            return

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

        logger.info(
            f"Cart abandonment notification sent - Phone: {cart.phone_number}, "
            f"Order Form: {cart.order_form_id}, Cart UUID: {cart.uuid}, "
            f"Project: {cart.project.name}"
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

        if status == "abandoned":
            cart.abandoned = True

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
            logger.error(f"Cart {cart_uuid} error: {error_message}")
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

    def _check_recent_purchases_for_cart_items(
        self, cart: Cart, recent_orders: list
    ) -> bool:
        """
        Check if any of the cart's items have been purchased in recent orders.

        This method:
        1. Extracts order IDs from recent orders
        2. Fetches detailed order information for each order
        3. Compares cart items with order items
        4. Returns True if any overlap is found

        Args:
            cart (Cart): The cart being processed.
            recent_orders (list): List of recent orders from the user.

        Returns:
            bool: True if any cart items were found in recent purchases.
        """
        cart_items = cart.config.get("cart_items", [])
        if not cart_items:
            logger.info(f"Cart {cart.uuid} has no products to compare")
            return False

        # Extract order IDs from recent orders
        order_ids = []
        for order in recent_orders:
            order_id = order.get("orderId")
            if order_id:
                order_ids.append(order_id)

        if not order_ids:
            logger.info(
                f"No valid order IDs found in recent orders for cart {cart.uuid}"
            )
            return False

        logger.info(
            f"Checking {len(order_ids)} recent orders for cart {cart.uuid}: {order_ids}"
        )

        # Store recent orders details for logging/debugging
        recent_orders_details = []

        # Fetch detailed order information for each order
        for order_id in order_ids:
            try:
                logger.info(f"Fetching details for order {order_id}")
                order_details = self._fetch_order_details_by_id(cart, order_id)
                if order_details:
                    # Store order details for logging
                    recent_orders_details.append(
                        {
                            "orderId": order_id,
                            "orderFormId": order_details.get("orderFormId"),
                            "items": order_details.get("itemMetadata", {}).get(
                                "Items", []
                            ),
                        }
                    )

                    if self._compare_cart_items_with_order_items(cart, order_details):
                        logger.info(
                            f"Found matching products in order {order_id} for cart {cart.uuid}"
                        )

                        # Store recent orders in cart config for debugging
                        cart.config["recent_orders_checked"] = recent_orders_details
                        cart.save()
                        logger.info(
                            f"Stored {len(recent_orders_details)} recent orders in cart config for debugging"
                        )

                        return True

            except CustomAPIException as e:
                logger.error(f"Error fetching order details for {order_id}: {str(e)}")
                continue

        # Store recent orders in cart config even if no match found (for debugging)
        cart.config["recent_orders_checked"] = recent_orders_details
        cart.save()
        logger.info(
            f"Stored {len(recent_orders_details)} recent orders in cart config (no matching products found)"
        )

        logger.info(f"No matching products found in recent orders for cart {cart.uuid}")
        return False

    def _check_identical_cart_sent_recently(self, cart: Cart) -> bool:
        """
        Check if a cart with identical items was already sent in the last 24 hours.

        This method:
        1. Gets current cart items
        2. Finds carts with same phone number sent in last 24 hours
        3. Compares items exactly (same products, same quantities)
        4. Returns True if identical cart was already sent

        Args:
            cart (Cart): The cart being processed.

        Returns:
            bool: True if identical cart was already sent recently.
        """
        cart_items = cart.config.get("cart_items", [])
        if not cart_items:
            logger.info(f"Cart {cart.uuid} has no products to compare")
            return False

        # Calculate 24 hours ago
        twenty_four_hours_ago = timezone.now() - timedelta(hours=24)

        # Find carts with same phone number that were sent in the last 24 hours
        recent_sent_carts = Cart.objects.filter(
            phone_number=cart.phone_number,
            project=cart.project,
            status="delivered_success",
            modified_on__gte=twenty_four_hours_ago,
        )

        if not recent_sent_carts:
            logger.info(f"No recent sent carts found for phone {cart.phone_number}")
            return False

        # Create a normalized representation of current cart items
        current_items_normalized = self._normalize_cart_items(cart_items)

        # Check each recent cart for identical items
        for recent_cart in recent_sent_carts:
            recent_items = recent_cart.config.get("cart_items", [])
            if recent_items:
                recent_items_normalized = self._normalize_cart_items(recent_items)
                logger.info(
                    f"Recent cart {recent_cart.uuid} items normalized: {recent_items_normalized}"
                )

                if current_items_normalized == recent_items_normalized:
                    logger.info(
                        f"Found identical cart {recent_cart.uuid} sent at {recent_cart.modified_on} "
                        f"for cart {cart.uuid}"
                    )
                    return True

        logger.info("No identical carts found in recent sent carts")
        return False

    def _normalize_cart_items(self, items: list) -> list:
        """
        Normalize cart items for comparison by extracting key identifiers.

        Args:
            items (list): List of cart items.

        Returns:
            list: Normalized list of item identifiers for comparison.
        """
        normalized = []
        for item in items:
            # Extract key identifiers: id, quantity
            normalized_item = {
                "id": str(item.get("id", "")),
                "quantity": item.get("quantity", 1),
            }
            normalized.append(normalized_item)

        # Sort by id to ensure consistent comparison
        normalized.sort(key=lambda x: x["id"])
        return normalized

    def _fetch_order_details_by_id(self, cart: Cart, order_id: str) -> dict:
        """
        Fetch detailed order information by order ID.

        Args:
            cart (Cart): The cart instance (used for project context).
            order_id (str): The order ID to fetch details for.

        Returns:
            dict: Complete order details, or empty dict if not found.
        """
        try:
            # Use the VTEX IO service to fetch order details
            order_details = self.vtex_io_service.get_order_details_by_id(
                account_domain=self._get_account_domain(str(cart.project.uuid)),
                order_id=order_id,
            )

            if order_details:
                item_count = len(order_details.get("itemMetadata", {}).get("Items", []))
                logger.info(
                    f"Successfully fetched order {order_id} with {item_count} items"
                )
                return order_details
            else:
                logger.warning(f"No order details found for order {order_id}")
                return {}

        except Exception as e:
            logger.error(f"Error fetching order details for {order_id}: {str(e)}")
            return {}

    def _compare_cart_items_with_order_items(
        self, cart: Cart, order_details: dict
    ) -> bool:
        """
        Compare cart items with order items to check for overlaps.

        Args:
            cart (Cart): The cart being processed.
            order_details (dict): Complete order details from API.

        Returns:
            bool: True if there's any overlap between cart and order items.
        """
        cart_items = cart.config.get("cart_items", [])
        order_items = order_details.get("itemMetadata", {}).get("Items", [])

        if not cart_items or not order_items:
            logger.info(
                f"Cart or order items empty - cart: {len(cart_items)}, order: {len(order_items)}"
            )
            return False

        # Create sets of item IDs for comparison
        cart_item_ids = set()
        order_item_ids = set()

        # Extract IDs from cart items
        for item in cart_items:
            if item.get("id"):
                cart_item_ids.add(str(item["id"]))

        # Extract IDs from order items (from itemMetadata.Items)
        for item in order_items:
            if item.get("Id"):  # Note: order items use "Id" (capital I)
                order_item_ids.add(str(item["Id"]))

        # Check for matching products between cart and recent orders
        matching_products = cart_item_ids.intersection(order_item_ids)

        if matching_products:
            logger.info(
                f"Found matching products in recent orders: {matching_products}"
            )
            return True

        logger.info("No matching products found in recent orders")
        return False

    def _check_abandoned_cart_notification_cooldown(self, cart: Cart) -> bool:
        """
        Check if there's an abandoned cart notification cooldown configured and if it should be applied.

        This method prevents sending multiple abandoned cart notifications to the same phone number
        within a configured time period. The goal is to maintain 1 notification per X hours.

        This method:
        1. Gets the cooldown configuration from integrated feature
        2. If configured, checks if any abandoned cart notification was sent recently
        3. Returns True if cooldown should be applied (skip notification)

        Args:
            cart (Cart): The cart being processed.

        Returns:
            bool: True if notification should be skipped due to cooldown.
        """
        # Get abandoned cart notification cooldown configuration from integrated feature
        cooldown_hours = cart.integrated_feature.config.get(
            "abandoned_cart_notification_cooldown_hours"
        )

        if not cooldown_hours:
            logger.info(
                f"No abandoned cart notification cooldown configured for cart {cart.uuid}"
            )
            return False

        # Calculate the cooldown period
        cooldown_period = timezone.now() - timedelta(hours=cooldown_hours)

        # Find any cart with same phone number that had abandoned cart notification sent within cooldown period
        recent_sent_cart = Cart.objects.filter(
            phone_number=cart.phone_number,
            project=cart.project,
            status="delivered_success",
            modified_on__gte=cooldown_period,
        ).first()

        if recent_sent_cart:
            logger.info(
                f"Abandoned cart notification cooldown applied for cart {cart.uuid} - "
                f"Phone {cart.phone_number} had abandoned cart notification sent at {recent_sent_cart.modified_on} "
                f"(cooldown: {cooldown_hours}h - maintaining 1 notification per {cooldown_hours} hours)"
            )
            return True

        logger.info(
            f"No recent abandoned cart notifications found for phone {cart.phone_number} "
            f"within {cooldown_hours}h cooldown"
        )
        return False


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
