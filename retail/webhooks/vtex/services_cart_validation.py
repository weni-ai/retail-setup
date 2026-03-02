import logging
from typing import Dict, Any, Union
from django.utils import timezone
from datetime import timedelta

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.features.models import IntegratedFeature
from retail.vtex.models import Cart
from retail.webhooks.vtex.utils import PhoneNotificationLockService
from retail.clients.vtex_io.client import VtexIOClient
from retail.services.vtex_io.service import VtexIOService


logger = logging.getLogger(__name__)


class CartValidationService:
    """
    Service for validating cart abandonment notifications.
    Works with both IntegratedFeature and IntegratedAgent configurations.
    """

    def __init__(self):
        self.vtex_io_service = VtexIOService(VtexIOClient())
        self.notification_lock_service = PhoneNotificationLockService()

    def should_process_cart_with_orders(
        self,
        cart: Cart,
        integration_config: Union[IntegratedFeature, IntegratedAgent],
        recent_orders: list,
    ) -> bool:
        """
        Perform all necessary validations before processing the cart, with pre-fetched orders.
        NOTE: Recent purchases validation should be done in the main flow, not here.

        Args:
            cart (Cart): The cart to validate.
            integration_config: Either IntegratedFeature or IntegratedAgent instance.
            recent_orders (list): List of recent orders from the user.

        Returns:
            bool: True if cart should be processed, False otherwise.
        """
        # Check if abandoned cart notification cooldown is configured and should be applied
        if self._check_abandoned_cart_notification_cooldown(cart, integration_config):
            logger.info(
                f"Skipping notification for cart {cart.uuid} - abandoned cart notification cooldown active"
            )
            self._update_cart_status(cart, "skipped_abandoned_cart_cooldown")
            return False

        # Check if identical cart was already sent recently
        if self._check_identical_cart_sent_recently(cart):
            logger.info(
                f"Skipping notification for cart {cart.uuid} - identical cart already sent recently"
            )
            self._update_cart_status(cart, "skipped_identical_cart")
            return False

        # NOTE: Recent purchases validation removed from here - should be done in main flow
        # like in the legacy _evaluate_orders method

        # Acquire lock to prevent multiple notifications for the same phone number
        if not self.notification_lock_service.acquire_lock(
            cart.phone_number, cart.uuid
        ):
            logger.info(
                f"Skipping notification for cart {cart.uuid} - "
                f"notification already in progress for phone {cart.phone_number}"
            )
            return False

        return True

    def should_process_cart(
        self, cart: Cart, integration_config: Union[IntegratedFeature, IntegratedAgent]
    ) -> bool:
        """
        Perform all necessary validations before processing the cart.

        Args:
            cart (Cart): The cart to validate.
            integration_config: Either IntegratedFeature or IntegratedAgent instance.

        Returns:
            bool: True if cart should be processed, False otherwise.
        """
        # Check if abandoned cart notification cooldown is configured and should be applied
        if self._check_abandoned_cart_notification_cooldown(cart, integration_config):
            logger.info(
                f"Skipping notification for cart {cart.uuid} - abandoned cart notification cooldown active"
            )
            self._update_cart_status(cart, "skipped_abandoned_cart_cooldown")
            return False

        # Check if identical cart was already sent recently
        if self._check_identical_cart_sent_recently(cart):
            logger.info(
                f"Skipping notification for cart {cart.uuid} - identical cart already sent recently"
            )
            self._update_cart_status(cart, "skipped_identical_cart")
            return False

        # Check if cart items were recently purchased
        if self._check_recent_purchases_for_cart_items(cart):
            logger.info(
                f"Cart {cart.uuid} items already purchased recently - marking as purchased"
            )
            self._update_cart_status(cart, "purchased")
            return False

        # Acquire lock to prevent multiple notifications for the same phone number
        if not self.notification_lock_service.acquire_lock(
            cart.phone_number, cart.uuid
        ):
            logger.info(
                f"Skipping notification for cart {cart.uuid} - "
                f"notification already in progress for phone {cart.phone_number}"
            )
            return False

        return True

    def _check_abandoned_cart_notification_cooldown(
        self, cart: Cart, integration_config: Union[IntegratedFeature, IntegratedAgent]
    ) -> bool:
        """
        Check if there's an abandoned cart notification cooldown configured and if it should be applied.

        Args:
            cart (Cart): The cart being processed.
            integration_config: Either IntegratedFeature or IntegratedAgent instance.

        Returns:
            bool: True if notification should be skipped due to cooldown.
        """
        # Get configuration from either integrated feature or integrated agent
        config = self._get_config(integration_config)
        cooldown_hours = config.get("abandoned_cart_notification_cooldown_hours")

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

    def _check_identical_cart_sent_recently(self, cart: Cart) -> bool:
        """
        Check if a cart with identical items was already sent in the last 24 hours.

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

    def _check_recent_purchases_for_cart_items(
        self, cart: Cart, recent_orders: list = None
    ) -> bool:
        """
        Check if any of the cart's items have been purchased in recent orders.

        Args:
            cart (Cart): The cart being processed.
            recent_orders (list, optional): List of recent orders from the user.
                                          If not provided, will fetch from cart config.

        Returns:
            bool: True if any cart items were found in recent purchases.
        """
        cart_items = cart.config.get("cart_items", [])
        if not cart_items:
            logger.info(f"Cart {cart.uuid} has no products to compare")
            return False

        # If recent_orders not provided, try to get from cart config or fetch them
        if recent_orders is None:
            # Try to get from cart config first (for agent flow)
            recent_orders = cart.config.get("recent_orders", [])

            if not recent_orders:
                # Fallback: fetch from API (for cases where orders weren't pre-fetched)
                client_profile = cart.config.get("client_profile", {})
                email = client_profile.get("email")
                if not email:
                    logger.info(f"No email found in cart {cart.uuid} config")
                    return False

                try:
                    project_uuid = str(cart.project.uuid)
                    orders = self.vtex_io_service.get_order_details(
                        account_domain=self._get_account_domain(project_uuid),
                        vtex_account=cart.project.vtex_account,
                        user_email=email,
                    )
                    recent_orders = orders.get("list", [])[:5] if orders else []
                except Exception as e:
                    logger.error(
                        f"Error fetching orders for cart {cart.uuid}: {str(e)}"
                    )
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

        # Check each order for matching items
        project_uuid = str(cart.project.uuid)
        for order_id in order_ids:
            try:
                logger.info(f"Fetching details for order {order_id}")
                order_details = self.vtex_io_service.get_order_details_by_id(
                    account_domain=self._get_account_domain(project_uuid),
                    vtex_account=cart.project.vtex_account,
                    order_id=order_id,
                )

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

            except Exception as e:
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

    def _get_config(
        self, integration_config: Union[IntegratedFeature, IntegratedAgent]
    ) -> Dict[str, Any]:
        """
        Get configuration from either IntegratedFeature or IntegratedAgent.

        Args:
            integration_config: Either IntegratedFeature or IntegratedAgent instance.

        Returns:
            Dict[str, Any]: The configuration dictionary.
        """
        # Both IntegratedFeature and IntegratedAgent have a config attribute
        return getattr(integration_config, "config", {}) or {}

    def _update_cart_status(
        self, cart: Cart, status: str, error_message: str = None
    ) -> None:
        """
        Update the cart's status and log errors if applicable.

        Args:
            cart (Cart): The cart to update.
            status (str): The new status to set.
            error_message (str, optional): Error message to log.
        """
        cart.status = status
        if status == "delivered_error" and error_message:
            cart.error_message = f"Broadcast failed: {error_message}"

        if status == "abandoned":
            cart.abandoned = True

        cart.save()

    def _get_account_domain(self, project_uuid: str) -> str:
        """
        Get account domain for VTEX IO service.

        Args:
            project_uuid (str): The project UUID.

        Returns:
            str: The account domain.
        """
        from django.core.cache import cache
        from retail.projects.models import Project

        cache_key = f"project_domain_{project_uuid}"
        cached_domain = cache.get(cache_key)

        if cached_domain:
            return cached_domain

        try:
            project = Project.objects.get(uuid=project_uuid)
            if not project.vtex_account:
                raise ValueError("VTEX account not defined for project.")

            domain = f"{project.vtex_account}.myvtex.com"
            cache.set(cache_key, domain, timeout=43200)  # 12 hours
            return domain
        except Project.DoesNotExist:
            raise ValueError("Project not found for given UUID.")
