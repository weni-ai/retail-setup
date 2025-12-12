import logging

from typing import Union, Tuple

from django.utils import timezone
from django.conf import settings

from datetime import timedelta

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.features.models import IntegratedFeature

from retail.vtex.models import Cart
from retail.vtex.usecases.base import BaseVtexUseCase

from retail.webhooks.vtex.utils import PhoneNotificationLockService
from retail.webhooks.vtex.usecases.typing import (
    CartAbandonmentDataDTO,
)

from retail.services.vtex_io.service import VtexIOService

from retail.services.code_actions.service import CodeActionsService
from retail.services.vtex.service import VtexService

from retail.clients.code_actions.client import CodeActionsClient
from retail.clients.vtex.client import VtexClient
from retail.clients.exceptions import CustomAPIException
from retail.clients.vtex_io.client import VtexIOClient


logger = logging.getLogger(__name__)


class CartAbandonmentService(BaseVtexUseCase):
    """
    Unified service for cart abandonment processing.
    This is the SINGLE SOURCE OF TRUTH for all cart abandonment rules.
    Works with both IntegratedFeature (legacy) and IntegratedAgent (new) configurations.

    All rules from CartAbandonmentUseCase are migrated here with full fidelity,
    but made flexible to work with both integration types.
    """

    def __init__(self):
        self.vtex_io_service = VtexIOService(VtexIOClient())
        self.notification_lock_service = PhoneNotificationLockService()

    def process_abandoned_cart(
        self, cart: Cart, integration_config: Union[IntegratedFeature, IntegratedAgent]
    ) -> None:
        """
        Process a cart marked as abandoned - MAIN ENTRY POINT.
        This method contains ALL the logic from CartAbandonmentUseCase.process_abandoned_cart

        Args:
            cart (Cart): The cart instance to process.
            integration_config: Either IntegratedFeature or IntegratedAgent instance.
        """
        try:
            logger.info(f"Starting abandoned cart processing for cart {cart.uuid}")

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
                        f"Cart {cart.uuid} is empty but project {project_uuid} "
                        f"(VTEX: {cart.project.vtex_account}) is configured to ignore empty carts - "
                        "continuing processing"
                    )
                    # Continue processing instead of marking as empty
                else:
                    # Mark cart as empty if no items are found (original behavior)
                    self._update_cart_status(cart, "empty")
                    logger.info(
                        f"Cart {cart.uuid} is empty - marking as empty (VTEX: {cart.project.vtex_account})"
                    )
                    return

            # Save cart items
            self._save_cart_items(cart, order_form)

            # Check orders by email
            orders = self._fetch_orders_by_email(cart, client_profile["email"])
            self._evaluate_orders(
                cart, orders, order_form, client_profile, integration_config
            )

            logger.info(f"Completed abandoned cart processing for cart {cart.uuid}")

        except Cart.DoesNotExist:
            logger.error(f"Cart with UUID {cart.uuid} does not exist.")
        except CustomAPIException as e:
            logger.error(f"API error while processing cart {cart.uuid}: {str(e)}")
            self._update_cart_status(cart, "delivered_error", str(e))
        except Exception as e:
            logger.exception(
                f"Unexpected error while processing cart {cart.uuid}: {str(e)}"
            )
            self._update_cart_status(cart, "delivered_error", str(e))

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
        self,
        cart: Cart,
        orders: dict,
        order_form: dict,
        client_profile: dict,
        integration_config: Union[IntegratedFeature, IntegratedAgent],
    ):
        """
        Evaluate orders and determine the status of the cart.

        Args:
            cart (Cart): The cart instance.
            orders (dict): List of orders retrieved.
            order_form (dict): Order form details.
            client_profile (dict): Client profile data.
            integration_config: Either IntegratedFeature or IntegratedAgent instance.
        """
        if not orders.get("list"):
            self._mark_cart_as_abandoned(
                cart, order_form, client_profile, integration_config
            )
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

        self._mark_cart_as_abandoned(
            cart, order_form, client_profile, integration_config
        )

    def _mark_cart_as_abandoned(
        self,
        cart: Cart,
        order_form: dict,
        client_profile: dict,
        integration_config: Union[IntegratedFeature, IntegratedAgent],
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
            integration_config: Either IntegratedFeature or IntegratedAgent instance.

        Returns:
            None
        """
        # Check if abandoned cart notification cooldown is configured and should be applied
        if self._check_abandoned_cart_notification_cooldown(cart, integration_config):
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

        # Collect all cart abandonment data in a unified structure
        cart_data = self._collect_cart_abandonment_data(
            cart, order_form, client_profile, integration_config
        )

        # For IntegratedAgent, we send raw data (DTO) without message structure.
        # For IntegratedFeature, we use the legacy flow with message structure.
        if isinstance(integration_config, IntegratedAgent):
            flow_type = "agent"
            flow_success = self._execute_agent_flow(cart, integration_config, cart_data)
        else:
            flow_type = "legacy"
            flow_success = self._execute_legacy_flow(
                cart, integration_config, cart_data
            )

        logger.info(
            f"Cart abandonment notification {'sent' if flow_success else 'failed'} "
            f"- flow={flow_type} phone={cart.phone_number} "
            f"order_form={cart.order_form_id} cart={cart.uuid} "
            f"project={cart.project.name}"
        )

    def _collect_cart_abandonment_data(
        self,
        cart: Cart,
        order_form: dict,
        client_profile: dict,
        integration_config: Union[IntegratedFeature, IntegratedAgent],
    ) -> CartAbandonmentDataDTO:
        """
        Collect all cart abandonment data in a unified DTO structure.
        This method extracts all necessary information for both agent and legacy flows.

        Args:
            cart (Cart): The cart instance.
            order_form (dict): Order form details.
            client_profile (dict): Client profile data.
            integration_config: Either IntegratedFeature or IntegratedAgent instance.

        Returns:
            CartAbandonmentDataDTO: Unified cart abandonment data structure.
        """
        config = self._get_config(integration_config)

        return CartAbandonmentDataDTO(
            # Cart basic info
            cart_uuid=str(cart.uuid),
            order_form_id=cart.order_form_id,
            phone_number=cart.phone_number,
            project_uuid=str(cart.project.uuid),
            vtex_account=cart.project.vtex_account,
            # Client info
            client_name=cart.config.get("client_name", ""),
            client_profile=client_profile,
            locale=cart.config.get("locale", "pt-BR"),
            # Cart content
            cart_items=cart.config.get("cart_items", []),
            total_value=self._calculate_total_value(cart),
            # Order form data
            order_form=order_form,
            # Configuration (only for legacy flow - agent flow gets these from AWS Lambda)
            template_name=config.get("abandoned_cart_template")
            if isinstance(integration_config, IntegratedFeature)
            else None,
            channel_uuid=config.get("flow_channel_uuid")
            if isinstance(integration_config, IntegratedFeature)
            else None,
            # Additional data
            cart_link=f"{cart.order_form_id}/",
            additional_data=cart.config,
        )

    def _execute_agent_flow(
        self,
        cart: Cart,
        integrated_agent: IntegratedAgent,
        cart_data: CartAbandonmentDataDTO,
    ) -> bool:
        """
        Execute the agent flow: webhook -> AWS Lambda -> Broadcast.
        Uses the centralized task to handle credentials and other centralized logic.
        Sends raw cart data without message structure.
        """
        logger.info(
            "CartAbandonmentService: executing AGENT flow for cart=%s agent=%s project=%s",
            cart.uuid,
            integrated_agent.uuid,
            cart.project.uuid,
        )
        try:
            # Use the centralized task to execute the agent webhook
            # This task handles credentials, centralized logic, and broadcast
            from retail.vtex.tasks import task_agent_webhook

            # Build minimal payload with only essential data for agent flow
            payload = {
                "cart_uuid": cart_data.cart_uuid,
                "order_form_id": cart_data.order_form_id,
                "phone_number": cart_data.phone_number,
                "client_name": cart_data.client_name,
                "project_uuid": cart_data.project_uuid,
                "vtex_account": cart_data.vtex_account,
            }
            logger.info(f"Payload sent to agent webhook: {payload}")

            task_agent_webhook(
                integrated_agent_uuid=str(integrated_agent.uuid),
                payload=payload,
                params={},  # Empty params - all data is in payload
            )

            self._update_cart_status(cart, "delivered_success")
            logger.info(
                "CartAbandonmentService: AGENT flow dispatched successfully for cart=%s",
                cart.uuid,
            )
            return True
        except Exception as exc:
            logger.exception(
                "CartAbandonmentService: AGENT flow failed for cart=%s error=%s",
                cart.uuid,
                exc,
            )
            self._update_cart_status(cart, "delivered_error", str(exc))
            return False

    def _execute_legacy_flow(
        self,
        cart: Cart,
        integrated_feature: IntegratedFeature,
        cart_data: CartAbandonmentDataDTO,
    ) -> bool:
        """
        Execute the legacy flow: code actions.
        Builds message structure from collected cart data.
        """
        logger.info(
            "CartAbandonmentService: executing LEGACY flow for cart=%s feature=%s project=%s",
            cart.uuid,
            integrated_feature.uuid,
            cart.project.uuid,
        )
        try:
            # Build message structure for legacy flow
            (
                message_payload,
                extra_parameters,
            ) = self._build_abandonment_message_from_data(cart_data)

            # Build full extra payload
            extra_payload = {
                "order_form": cart_data.order_form,
                "client_profile": cart_data.client_profile,
                **extra_parameters,  # Include extra message context
            }

            code_actions_service = CodeActionsService(CodeActionsClient())

            response = code_actions_service.run_code_action(
                action_id=self._get_code_action_id_by_cart(integrated_feature),
                message_payload=message_payload,
                extra_payload=extra_payload,
            )

            self._update_cart_status(cart, "delivered_success", response)
            self._set_utm_source(cart)
            logger.info(
                "CartAbandonmentService: LEGACY flow delivered_success for cart=%s",
                cart.uuid,
            )
            return True
        except Exception as exc:
            logger.exception(
                "CartAbandonmentService: LEGACY flow failed for cart=%s error=%s",
                cart.uuid,
                exc,
            )
            self._update_cart_status(cart, "delivered_error", str(exc))
            return False

    def _build_abandonment_message_from_data(
        self, cart_data: CartAbandonmentDataDTO
    ) -> Tuple[dict, dict]:
        """
        Build the message payload and extra parameters for legacy flow from collected data.
        This method is ONLY used for IntegratedFeature (legacy flow).
        Agent flow gets template_name and channel_uuid from AWS Lambda.

        Args:
            cart_data (CartAbandonmentDataDTO): Collected cart abandonment data.

        Returns:
            tuple: (message_payload, extra_parameters)
        """
        template_name = cart_data.template_name
        channel_uuid = cart_data.channel_uuid
        client_name = cart_data.client_name
        locale = cart_data.locale
        cart_link = cart_data.cart_link

        message_payload = {
            "project": cart_data.project_uuid,
            "urns": [f"whatsapp:{cart_data.phone_number}"],
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
            "project_uuid": cart_data.project_uuid,
            "flow_channel_uuid": channel_uuid,
            "client_name": client_name,
            "locale": locale,
            "cart_link": cart_link,
        }

        return message_payload, extra_parameters

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

    def _normalize_cart_items(self, cart_items: list) -> set:
        """
        Normalize cart items for comparison.

        Args:
            cart_items (list): List of cart items.

        Returns:
            set: Normalized set of item identifiers.
        """
        normalized_items = set()
        for item in cart_items:
            item_id = item.get("id")
            if item_id:
                normalized_items.add(str(item_id))
        return normalized_items

    def _get_config(
        self, integration_config: Union[IntegratedFeature, IntegratedAgent]
    ) -> dict:
        """
        Get configuration from either IntegratedFeature or IntegratedAgent.

        Args:
            integration_config: Either IntegratedFeature or IntegratedAgent instance.

        Returns:
            dict: Configuration dictionary.
        """
        return getattr(integration_config, "config", {}) or {}

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

    def _calculate_total_value(self, cart: Cart) -> float:
        """
        Calculate total value from cart items.

        Args:
            cart (Cart): The cart instance.

        Returns:
            float: Total value of cart items.
        """
        cart_items = cart.config.get("cart_items", [])
        total = 0.0

        for item in cart_items:
            price = item.get("price", 0)
            quantity = item.get("quantity", 1)
            total += price * quantity

        return total

    def _get_code_action_id_by_cart(self, integrated_feature: IntegratedFeature) -> str:
        """
        Get the code action ID for the cart based on feature type.

        Args:
            integrated_feature (IntegratedFeature): The integrated feature.

        Returns:
            str: The code action ID.

        Raises:
            ValueError: If integrated feature, vtex account or action ID is not found.
        """
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

    def _set_utm_source(self, cart: Cart):
        """
        Set UTM source for the cart.
        """
        vtex_service = VtexService(VtexClient())
        domain = self._get_account_domain(str(cart.project.uuid))
        vtex_service.set_order_form_marketing_data(
            domain, cart.order_form_id, "weniabandonedcart"
        )
