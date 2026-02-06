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


def _build_log_context(cart: Cart, integration_config=None) -> str:
    """Build a standardized log context string for cart operations."""
    vtex_account = cart.project.vtex_account if cart.project else "unknown"
    project_uuid = str(cart.project.uuid) if cart.project else "unknown"

    context = (
        f"vtex_account={vtex_account} cart_uuid={cart.uuid} "
        f"phone={cart.phone_number} project_uuid={project_uuid} "
        f"order_form={cart.order_form_id}"
    )

    if integration_config:
        if isinstance(integration_config, IntegratedAgent):
            context += f" integration_type=agent agent_uuid={integration_config.uuid}"
        elif isinstance(integration_config, IntegratedFeature):
            context += (
                f" integration_type=feature feature_uuid={integration_config.uuid}"
            )

    return context


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
        log_context = _build_log_context(cart, integration_config)

        try:
            logger.info(f"[CART_SERVICE] Starting processing: {log_context}")

            # Fetch order form details from VTEX IO
            order_form = self._fetch_order_form(cart)
            logger.info(
                f"[CART_SERVICE] Order form fetched: {log_context} "
                f"items_count={len(order_form.get('items', []))}"
            )

            # Process and update cart information
            client_profile = self._extract_client_profile_and_save_locale(
                cart, order_form
            )
            client_email = client_profile.get("email")

            # Email is required to fetch orders and continue processing
            if not client_email:
                logger.info(
                    f"[CART_SERVICE] Client email not found: {log_context} "
                    f"reason=email_not_in_order_form final_status=empty"
                )
                self._update_cart_status(cart, "empty")
                return

            logger.info(
                f"[CART_SERVICE] Client profile extracted: {log_context} "
                f"email={client_email}"
            )

            if not order_form.get("items", []):
                # Check if this project should ignore empty cart validation
                project_uuid = str(cart.project.uuid)
                ignore_empty_carts_projects = getattr(
                    settings, "IGNORE_EMPTY_CARTS_FOR_PROJECTS", []
                )

                if project_uuid in ignore_empty_carts_projects:
                    logger.info(
                        f"[CART_SERVICE] Empty cart but project whitelisted: {log_context} "
                        f"reason=project_in_IGNORE_EMPTY_CARTS_FOR_PROJECTS action=continue_processing"
                    )
                    # Continue processing instead of marking as empty
                else:
                    # Mark cart as empty if no items are found (original behavior)
                    self._update_cart_status(cart, "empty")
                    logger.info(
                        f"[CART_SERVICE] Cart is empty: {log_context} "
                        f"reason=no_items_in_order_form final_status=empty"
                    )
                    return

            # Save cart items
            cart_items = order_form.get("items", [])
            self._save_cart_items(cart, order_form)
            logger.info(
                f"[CART_SERVICE] Cart items saved: {log_context} "
                f"items_count={len(cart_items)}"
            )

            # Check orders by email (email already validated above)
            orders = self._fetch_orders_by_email(cart, client_email)
            orders_count = len(orders.get("list", []))
            logger.info(
                f"[CART_SERVICE] Orders fetched by email: {log_context} "
                f"email={client_email} orders_found={orders_count}"
            )

            self._evaluate_orders(
                cart, orders, order_form, client_profile, integration_config
            )

            logger.info(f"[CART_SERVICE] Completed processing: {log_context}")

        except Cart.DoesNotExist:
            logger.error(
                f"[CART_SERVICE] Cart not found: {log_context} "
                f"reason=cart_does_not_exist"
            )
        except CustomAPIException as e:
            logger.error(
                f"[CART_SERVICE] API error: {log_context} "
                f"error={str(e)} final_status=delivered_error"
            )
            self._update_cart_status(cart, "delivered_error", str(e))
        except Exception as e:
            logger.exception(
                f"[CART_SERVICE] Unexpected error: {log_context} "
                f"error={str(e)} final_status=delivered_error"
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
        project_uuid = str(cart.project.uuid)
        order_form = self.vtex_io_service.get_order_form_details(
            account_domain=self._get_account_domain(project_uuid),
            project_uuid=project_uuid,
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
        project_uuid = str(cart.project.uuid)
        orders = self.vtex_io_service.get_order_details(
            account_domain=self._get_account_domain(project_uuid),
            project_uuid=project_uuid,
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
        log_context = _build_log_context(cart, integration_config)

        if not orders.get("list"):
            logger.info(
                f"[CART_SERVICE] No orders found for client: {log_context} "
                f"action=mark_as_abandoned reason=client_has_no_orders"
            )
            self._mark_cart_as_abandoned(
                cart, order_form, client_profile, integration_config
            )
            return

        recent_orders = orders.get("list", [])[:5]

        # if self._check_recent_purchases_for_cart_items(cart, recent_orders):
        #     logger.info(
        #         f"[CART_SERVICE] Cart items already purchased: {log_context} "
        #         f"final_status=purchased reason=items_found_in_recent_orders"
        #     )
        #     self._update_cart_status(cart, "purchased")
        #     return

        logger.info(
            f"[CART_SERVICE] Orders found but items not purchased: {log_context} "
            f"recent_orders_checked={len(recent_orders)} action=mark_as_abandoned"
        )
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
        log_context = _build_log_context(cart, integration_config)
        cart_value = self._calculate_total_value(cart)
        items_count = len(cart.config.get("cart_items", []))

        logger.info(
            f"[CART_SERVICE] Evaluating cart for notification: {log_context} "
            f"cart_value={cart_value} items_count={items_count}"
        )

        # For IntegratedAgent, check minimum cart value before processing
        if isinstance(integration_config, IntegratedAgent):
            if self._check_minimum_cart_value(cart, integration_config):
                # Log is already inside the method, just return
                return

        # Check if abandoned cart notification cooldown is configured and should be applied
        if self._check_abandoned_cart_notification_cooldown(cart, integration_config):
            logger.info(
                f"[CART_SERVICE] SKIP - Cooldown active: {log_context} "
                f"final_status=skipped_abandoned_cart_cooldown reason=notification_cooldown_active"
            )
            self._update_cart_status(cart, "skipped_abandoned_cart_cooldown")
            return

        # Check if identical cart was already sent recently
        if self._check_identical_cart_sent_recently(cart):
            logger.info(
                f"[CART_SERVICE] SKIP - Identical cart: {log_context} "
                f"final_status=skipped_identical_cart reason=identical_cart_sent_within_24h"
            )
            self._update_cart_status(cart, "skipped_identical_cart")
            return

        # Acquire lock to prevent multiple notifications for the same phone number
        if not self.notification_lock_service.acquire_lock(
            cart.phone_number, cart.uuid
        ):
            logger.info(
                f"[CART_SERVICE] SKIP - Lock failed: {log_context} "
                f"reason=notification_already_in_progress_for_phone"
            )
            return

        logger.info(
            f"[CART_SERVICE] All checks passed, marking as abandoned: {log_context}"
        )
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
            f"[CART_SERVICE] Notification {'SENT' if flow_success else 'FAILED'}: {log_context} "
            f"flow_type={flow_type} final_status={cart.status}"
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

        Includes agent configuration in the payload:
        - image_config: Contains header_image_type for template image selection
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

            # Get abandoned cart configuration for agent
            abandoned_cart_config = self._get_abandoned_cart_config(integrated_agent)

            # Build image configuration for the agent
            # Allows the CLI agent to determine which image to use in the template
            # Also validates if template actually supports image headers
            image_config = self._build_image_config(
                abandoned_cart_config, cart_data, integrated_agent
            )

            # Build payload with essential data and configuration for agent flow
            payload = {
                "cart_uuid": cart_data.cart_uuid,
                "order_form_id": cart_data.order_form_id,
                "phone_number": cart_data.phone_number,
                "client_name": cart_data.client_name,
                "project_uuid": cart_data.project_uuid,
                "vtex_account": cart_data.vtex_account,
                # Agent configuration
                "image_config": image_config,
                # Cart items for image selection logic in the agent
                "cart_items": cart_data.cart_items,
            }

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

    def _build_image_config(
        self,
        abandoned_cart_config: dict,
        cart_data: CartAbandonmentDataDTO,
        integrated_agent: IntegratedAgent,
    ) -> dict:
        """
        Build the image configuration to send to the agent.

        The agent will use this configuration to determine which image to include
        in the template header.

        This method also validates if the template actually supports image headers.
        If the template doesn't have an image header, it forces 'no_image' regardless
        of the user's configuration.

        Args:
            abandoned_cart_config (dict): Abandoned cart config from IntegratedAgent.
            cart_data (CartAbandonmentDataDTO): Cart data with items.
            integrated_agent (IntegratedAgent): The integrated agent instance.

        Returns:
            dict: Image configuration with type and any pre-computed data.
        """
        header_image_type = abandoned_cart_config.get("header_image_type", "first_item")

        # Valid options:
        # - "first_item": Use first item's image from cart
        # - "most_expensive": Use most expensive item's image from cart
        # - "no_image": No image header (user explicitly chose not to use image)
        valid_image_types = ("first_item", "most_expensive", "no_image")

        if header_image_type not in valid_image_types:
            logger.warning(
                f"Invalid header_image_type '{header_image_type}', "
                f"valid options are {valid_image_types}. Falling back to 'first_item'"
            )
            header_image_type = "first_item"

        # Validate if template actually supports image header
        # If template doesn't have image header, force 'no_image' to avoid errors
        if header_image_type != "no_image":
            template_has_image = self._check_template_has_image_header(integrated_agent)
            if not template_has_image:
                logger.info(
                    f"Template for agent {integrated_agent.uuid} doesn't have image header. "
                    f"Forcing image_config to 'no_image' (config was '{header_image_type}')"
                )
                header_image_type = "no_image"

        return {
            "type": header_image_type,
            # Additional image-related config can be added here in the future
        }

    def _check_template_has_image_header(
        self, integrated_agent: IntegratedAgent
    ) -> bool:
        """
        Check if the agent's template has an image header.

        Args:
            integrated_agent (IntegratedAgent): The integrated agent instance.

        Returns:
            bool: True if template has image header, False otherwise.
        """
        # Get the first active template for this agent
        template = integrated_agent.templates.filter(is_active=True).first()

        if not template:
            logger.warning(
                f"No active template found for agent {integrated_agent.uuid}"
            )
            return False

        # Check if template metadata has an image header
        metadata = template.metadata or {}
        header = metadata.get("header")

        if not header:
            return False

        # Header can be a dict with header_type or just a string (for TEXT)
        if isinstance(header, dict):
            return header.get("header_type") == "IMAGE"

        # If header is a string, it's TEXT type
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

    def _check_minimum_cart_value(
        self, cart: Cart, integration_config: IntegratedAgent
    ) -> bool:
        """
        Check if the cart value meets the minimum threshold for notification.

        Only applies to IntegratedAgent. Extracts minimum_cart_value from
        config['abandoned_cart']['minimum_cart_value'].

        Args:
            cart (Cart): The cart being processed.
            integration_config (IntegratedAgent): The integrated agent instance.

        Returns:
            bool: True if notification should be skipped (cart value below minimum).
        """
        log_context = _build_log_context(cart, integration_config)
        abandoned_cart_config = self._get_abandoned_cart_config(integration_config)
        minimum_value = abandoned_cart_config.get("minimum_cart_value")

        if minimum_value is None:
            logger.info(
                f"[CART_SERVICE] Minimum value not configured: {log_context} "
                f"action=skip_value_check reason=minimum_cart_value_not_set"
            )
            return False

        cart_total = self._calculate_total_value(cart)
        # VTEX stores values in cents, convert to BRL
        cart_total_brl = cart_total / 100

        if cart_total_brl < minimum_value:
            logger.info(
                f"[CART_SERVICE] SKIP - Below minimum value: {log_context} "
                f"cart_value_brl={cart_total_brl:.2f} minimum_value_brl={minimum_value:.2f} "
                f"final_status=skipped_below_minimum_value reason=cart_value_below_threshold"
            )
            self._update_cart_status(cart, "skipped_below_minimum_value")
            return True

        logger.info(
            f"[CART_SERVICE] Minimum value check passed: {log_context} "
            f"cart_value_brl={cart_total_brl:.2f} minimum_value_brl={minimum_value:.2f}"
        )
        return False

    def _get_abandoned_cart_config(self, integration_config: IntegratedAgent) -> dict:
        """
        Get the abandoned cart specific configuration from IntegratedAgent.

        Args:
            integration_config (IntegratedAgent): The integrated agent instance.

        Returns:
            dict: Abandoned cart configuration or empty dict if not found.
        """
        config = getattr(integration_config, "config", {}) or {}
        return config.get("abandoned_cart", {})

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
        log_context = _build_log_context(cart, integration_config)

        # Get configuration from either integrated feature or integrated agent
        # For IntegratedAgent, check abandoned_cart config first
        if isinstance(integration_config, IntegratedAgent):
            abandoned_cart_config = self._get_abandoned_cart_config(integration_config)
            cooldown_hours = abandoned_cart_config.get("notification_cooldown_hours")
        else:
            config = self._get_config(integration_config)
            cooldown_hours = config.get("abandoned_cart_notification_cooldown_hours")

        if not cooldown_hours:
            logger.info(
                f"[CART_SERVICE] Cooldown not configured: {log_context} "
                f"check=notification_cooldown result=skip_check"
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
                f"[CART_SERVICE] Cooldown check FAILED: {log_context} "
                f"cooldown_hours={cooldown_hours} "
                f"previous_cart_uuid={recent_sent_cart.uuid} "
                f"previous_sent_at={recent_sent_cart.modified_on} "
                f"reason=notification_sent_within_cooldown_period"
            )
            return True

        logger.info(
            f"[CART_SERVICE] Cooldown check PASSED: {log_context} "
            f"cooldown_hours={cooldown_hours} reason=no_recent_notifications"
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
        log_context = _build_log_context(cart)

        cart_items = cart.config.get("cart_items", [])
        if not cart_items:
            logger.info(
                f"[CART_SERVICE] Identical cart check skipped: {log_context} "
                f"reason=no_cart_items_to_compare"
            )
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

        recent_count = recent_sent_carts.count()
        if not recent_sent_carts:
            logger.info(
                f"[CART_SERVICE] Identical cart check PASSED: {log_context} "
                f"reason=no_recent_sent_carts_for_phone"
            )
            return False

        # Create a normalized representation of current cart items
        current_items_normalized = self._normalize_cart_items(cart_items)
        logger.info(
            f"[CART_SERVICE] Checking for identical cart: {log_context} "
            f"current_items={current_items_normalized} recent_carts_to_check={recent_count}"
        )

        # Check each recent cart for identical items
        for recent_cart in recent_sent_carts:
            recent_items = recent_cart.config.get("cart_items", [])
            if recent_items:
                recent_items_normalized = self._normalize_cart_items(recent_items)

                if current_items_normalized == recent_items_normalized:
                    logger.info(
                        f"[CART_SERVICE] Identical cart check FAILED: {log_context} "
                        f"matching_cart_uuid={recent_cart.uuid} "
                        f"matching_cart_sent_at={recent_cart.modified_on} "
                        f"matching_items={recent_items_normalized} "
                        f"reason=identical_cart_sent_within_24h"
                    )
                    return True

        logger.info(
            f"[CART_SERVICE] Identical cart check PASSED: {log_context} "
            f"carts_compared={recent_count} reason=no_identical_items_found"
        )
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
            project_uuid = str(cart.project.uuid)
            order_details = self.vtex_io_service.get_order_details_by_id(
                account_domain=self._get_account_domain(project_uuid),
                project_uuid=project_uuid,
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

        # Record the exact timestamp when notification was successfully sent
        if status == "delivered_success":
            cart.notification_sent_at = timezone.now()

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
