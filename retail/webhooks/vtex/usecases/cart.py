import logging
import time

from typing import Any, Dict, Optional

from rest_framework.exceptions import ValidationError
from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.vtex.tasks import task_abandoned_cart_update
from django_redis import get_redis_connection

from django.conf import settings

from retail.webhooks.vtex.services import (
    CartTimeRestrictionService,
    CartPhoneRestrictionService,
    CartServiceContext,
)
from retail.agents.domains.agent_webhook.usecases.base_agent_webhook import (
    BaseAgentWebhookUseCase,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent


logger = logging.getLogger(__name__)


def generate_task_key(cart_uuid: str) -> str:
    """
    Generate a deterministic task key using the cart UUID.
    """
    return f"abandonment-task-{cart_uuid}"


class CartUseCase(BaseAgentWebhookUseCase):
    """
    Centralized use case for handling cart actions.
    """

    def __init__(self, account: str):
        super().__init__()
        self.account = account
        self.project = self._get_project_by_account()
        self.integrated_feature = self._get_integrated_feature()
        self.integrated_agent = self._get_integrated_agent()

    def _get_integrated_agent(self) -> Optional[IntegratedAgent]:
        """
        Retrieve the integrated agent for abandoned cart if it exists.

        Returns:
            Optional[IntegratedAgent]: The integrated agent if found, otherwise None.
        """
        if not self.project:
            return None

        if not settings.ABANDONED_CART_AGENT_UUID:
            logger.info("ABANDONED_CART_AGENT_UUID is not set in settings.")
            return None

        return self.get_integrated_agent_if_exists(
            self.project, settings.ABANDONED_CART_AGENT_UUID
        )

    def _get_project_by_account(self) -> Optional[Project]:
        """
        Fetch the project associated with the account.

        Returns:
            Optional[Project]: The associated project instance.
        """
        return self.get_project_by_vtex_account(self.account)

    def _get_integrated_feature(self) -> Optional[IntegratedFeature]:
        """
        Retrieve the IntegratedFeature for the abandoned cart notification feature
        associated with the current project.

        This method fetches the `IntegratedFeature` associated with the abandoned cart
        functionality for the project linked to this use case.

        Returns:
            Optional[IntegratedFeature]: The integrated feature instance for the abandoned cart, or None if not found.
        """
        if not self.project:
            return None

        try:
            feature = Feature.objects.get(
                can_vtex_integrate=True, code="abandoned_cart"
            )
            return IntegratedFeature.objects.get(project=self.project, feature=feature)
        except Feature.DoesNotExist:
            logger.info("Feature with code 'abandoned_cart' not found.")
            return None
        except IntegratedFeature.DoesNotExist:
            logger.info(
                f"IntegratedFeature for project '{self.project}' and feature "
                f"'abandoned_cart' not found."
            )
            return None
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while retrieving the feature: {str(e)}"
            )
            return None

    def process_cart_notification(
        self, order_form_id: str, phone: str, name: str
    ) -> Cart:
        """
        Process incoming cart notification, renewing task or creating new cart.

        Args:
            order_form_id (str): The unique identifier for the cart.

        Returns:
            Cart: The created or updated cart instance.
        """
        # Get Redis connection for distributed lock
        redis = get_redis_connection()
        lock_key = f"cart_creation_lock:{self.account}:{order_form_id}:{phone}"

        # Try to acquire distributed lock (30 seconds TTL)
        if not redis.set(lock_key, "locked", nx=True, ex=30):
            logger.info(f"Cart creation already in progress for {order_form_id}")
            # Wait a bit and try to get the existing cart
            time.sleep(1)
            try:
                return Cart.objects.get(
                    order_form_id=order_form_id,
                    project=self.project,
                    phone_number=phone,
                    status="created",
                )
            except Cart.DoesNotExist:
                raise ValidationError(f"Cart creation failed to lock {lock_key}")

        try:
            # Check if the cart already exists
            cart = Cart.objects.get(
                order_form_id=order_form_id,
                project=self.project,
                phone_number=phone,
                status="created",
            )
            # Renew abandonment task
            self._schedule_abandonment_task(str(cart.uuid))
            return cart
        except Cart.DoesNotExist:
            # Create new cart if it doesn't exist
            return self._create_cart(order_form_id, phone, name)
        except Exception as e:
            logger.error(
                f"Unexpected error processing cart notification: {str(e)}",
                exc_info=True,
            )
            raise
        finally:
            # Release the lock
            redis.delete(lock_key)

    def _create_service_context(
        self, entity_type: str, entity_uuid: str, config: Dict[str, Any]
    ) -> CartServiceContext:
        """
        Create a service context for cart services.

        Args:
            entity_type (str): Type of entity ('integrated_feature' or 'integrated_agent')
            entity_uuid (str): UUID of the entity
            config (Dict[str, Any]): Configuration dictionary

        Returns:
            CartServiceContext: The service context
        """
        return CartServiceContext(
            project_uuid=str(self.project.uuid),
            config=config,
            entity_type=entity_type,
            entity_uuid=entity_uuid,
        )

    def _validate_phone_restriction(
        self,
        phone: str,
        order_form_id: str,
        entity_type: str,
        entity_uuid: str,
        config: Dict[str, Any],
    ) -> None:
        """
        Validate phone restriction for cart creation.

        Args:
            phone (str): Phone number to validate
            order_form_id (str): Order form ID for context
            entity_type (str): Type of entity ('integrated_feature' or 'integrated_agent')
            entity_uuid (str): UUID of the entity
            config (Dict[str, Any]): Configuration dictionary

        Raises:
            ValidationError: If phone is not allowed due to restrictions
        """
        context = self._create_service_context(entity_type, entity_uuid, config)
        phone_restriction_service = CartPhoneRestrictionService(context)

        if not phone_restriction_service.validate_phone_restriction(phone):
            logger.info(
                f"Cart creation blocked for phone {phone} due to phone restriction. "
                f"Order form: {order_form_id}, Project: {self.project.uuid}"
            )
            raise ValidationError(
                {
                    "error": "Phone number not allowed due to active restrictions",
                    "phone": phone,
                    "order_form_id": order_form_id,
                    "project_uuid": str(self.project.uuid),
                    "message": "Cart creation blocked due to active phone restrictions.",
                },
                code="phone_restriction_blocked",
            )

    def _create_cart(self, order_form_id: str, phone: str, name: str) -> Cart:
        """
        Create a new cart entry and schedule an abandonment task.

        Args:
            order_form_id (str): The UUID of the cart.
            phone (str): The phone number.
            name (str): The client name.

        Returns:
            Cart: The created cart instance.

        Raises:
            ValidationError: If phone restriction is active and phone is not allowed.
        """
        # Decide whether to use integrated agent or integrated feature
        if self.integrated_agent:
            logger.info(
                f"Using integrated agent for cart creation. Project: {self.project.uuid}"
            )
            return self._create_cart_with_agent(order_form_id, phone, name)
        elif self.integrated_feature:
            logger.info(
                f"Using integrated feature for cart creation. Project: {self.project.uuid}"
            )
            return self._create_cart_with_feature(order_form_id, phone, name)
        else:
            logger.warning(
                f"No integrated agent or feature found for project: {self.project.uuid}"
            )
            raise ValidationError(
                {"error": "No abandoned cart integration configured"},
                code="no_integration_configured",
            )

    def _create_cart_with_agent(
        self, order_form_id: str, phone: str, name: str
    ) -> Cart:
        """
        Create a cart using integrated agent (new flow).
        """
        # Validate phone restriction before creating cart (same as feature flow)
        self._validate_phone_restriction(
            phone,
            order_form_id,
            "integrated_agent",
            str(self.integrated_agent.uuid),
            self.integrated_agent.config,
        )

        cart = Cart.objects.create(
            order_form_id=order_form_id,
            status="created",
            project=self.project,
            integrated_agent=self.integrated_agent,
            phone_number=phone,
            config={"client_name": name},
        )

        # Schedule abandonment task
        self._schedule_abandonment_task(str(cart.uuid))
        return cart

    def _create_cart_with_feature(
        self, order_form_id: str, phone: str, name: str
    ) -> Cart:
        """
        Create a cart using integrated feature (legacy flow).
        """
        # Check if templates are synchronized before proceeding
        sync_status = self.integrated_feature.config.get(
            "templates_synchronization_status", "pending"
        )

        if sync_status != "synchronized":
            logger.info(
                f"Templates are not ready (status: {sync_status}) for project {self.project.uuid}. "
                f"Skipping cart creation for order form {order_form_id}."
            )
            raise ValidationError(
                {"error": "Templates are not synchronized"},
                code="templates_not_synchronized",
            )

        # Validate phone restriction before creating cart
        self._validate_phone_restriction(
            phone,
            order_form_id,
            "integrated_feature",
            str(self.integrated_feature.uuid),
            self.integrated_feature.config,
        )

        cart = Cart.objects.create(
            order_form_id=order_form_id,
            status="created",
            project=self.project,
            integrated_feature=self.integrated_feature,
            phone_number=phone,
            config={"client_name": name},
        )

        # Schedule abandonment task
        self._schedule_abandonment_task(str(cart.uuid))
        return cart

    def _schedule_abandonment_task(self, cart_uuid: str):
        """
        Schedule a task to mark a cart as abandoned after the configured time.

        Args:
            cart_uuid (str): The UUID of the cart.
        """
        # Determine which integration to use and create context
        if self.integrated_agent:
            context = self._create_service_context(
                "integrated_agent",
                str(self.integrated_agent.uuid),
                self.integrated_agent.config,
            )
            integration_type = "agent"
        elif self.integrated_feature:
            context = self._create_service_context(
                "integrated_feature",
                str(self.integrated_feature.uuid),
                self.integrated_feature.config,
            )
            integration_type = "feature"
        else:
            # No integration configured - should not proceed
            error_message = (
                "No abandoned cart integration configured for project "
                f"{self.project.uuid}. Cannot schedule abandonment task."
            )
            logger.error(error_message)
            raise ValidationError(
                {"error": "No abandoned cart integration configured"},
                code="no_integration_configured",
            )

        # Schedule the task using the determined context
        task_key = generate_task_key(cart_uuid)
        time_restriction_service = CartTimeRestrictionService(context)
        countdown = time_restriction_service.get_countdown()

        logger.info(
            f"Scheduling task for cart {cart_uuid} with {integration_type} flow, countdown {countdown}"
        )

        task_abandoned_cart_update.apply_async(
            (cart_uuid,), countdown=countdown, task_id=task_key
        )
