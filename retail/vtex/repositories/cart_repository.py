import logging

from typing import Optional
from uuid import UUID

from django.utils import timezone

from retail.projects.models import Project
from ..models import Cart


logger = logging.getLogger(__name__)


class CartRepository:
    """Abstraction over Cart persistence."""

    @staticmethod
    def find_by_order_form(order_form_id: str, project: Project) -> Optional[Cart]:
        """
        Retrieve a cart by its VTEX order-form identifier, only if it is linked to a flows channel.

        This method fetches a cart based on the provided VTEX order-form ID and project.
        It only returns the cart instance if it is explicitly linked to a flows channel
        via the `flows_channel_uuid` field. If the cart does not exist or is not linked
        to a flows channel, returns None.

        Args:
            order_form_id: The VTEX order-form ID.
            project: The project instance.

        Returns:
            The matching :class:`Cart` instance if linked to a flows channel, or ``None`` if not found or not linked.
        """
        cart = Cart.objects.filter(order_form_id=order_form_id, project=project).first()
        if cart:
            # Check if flows_channel_uuid exists and is not None
            if cart.flows_channel_uuid:
                logger.info(
                    f"Cart found with order_form_id={order_form_id} and flows_channel_uuid={cart.flows_channel_uuid}."
                )
                return cart
            else:
                logger.info(
                    f"Cart found with order_form_id={order_form_id} but does not have flows_channel_uuid set."
                )

        return None

    @staticmethod
    def create(
        order_form_id: str,
        project: Project,
        flows_channel_uuid: UUID,
    ) -> Cart:
        """
        Create and persist a new cart with the required fields.

        Args:
            order_form_id: The VTEX order-form ID.
            project: The project instance.
        Returns:
            The newly created :class:`Cart` instance.
        """
        cart = Cart.objects.create(
            order_form_id=order_form_id,
            project=project,
            flows_channel_uuid=flows_channel_uuid,
        )
        logger.info(
            f"Cart created with uuid={cart.uuid}, order_form_id={order_form_id}, "
            f"project={project.uuid}, flows_channel_uuid={flows_channel_uuid}."
        )
        return cart

    @staticmethod
    def update_status(cart: Cart, new_status: str) -> Cart:
        """
        Updates the status of the provided cart.

        Args:
            cart: The Cart instance to update.
            new_status: The new status string ("purchased", etc).

        Returns:
            The updated Cart instance.
        """
        cart.status = new_status
        cart.save(update_fields=["status", "modified_on"])
        logger.info(f"Cart status updated to '{new_status}' for cart {cart.uuid}.")
        return cart

    @staticmethod
    def update_capi_notification_sent(cart: Cart) -> Cart:
        """
        Updates the notification sent to CAPI field of the provided cart.
        """
        cart.capi_notification_sent = True
        cart.save(update_fields=["capi_notification_sent"])
        logger.info(f"Cart {cart.uuid} notification sent to CAPI.")
        return cart

    @staticmethod
    def mark_notification_sent(cart: Cart) -> Cart:
        """
        Mark the cart as having successfully sent the abandonment notification.

        This method:
        1. Sets status to 'delivered_success'
        2. Sets notification_sent_at to current timestamp

        This ensures we have a reliable timestamp for when the notification
        was actually sent, separate from the auto-updated modified_on field.

        Args:
            cart: The Cart instance to update.

        Returns:
            The updated Cart instance.
        """
        cart.status = "delivered_success"
        cart.notification_sent_at = timezone.now()
        cart.save(update_fields=["status", "notification_sent_at", "modified_on"])
        logger.info(
            f"Cart {cart.uuid} marked as notification sent at {cart.notification_sent_at}."
        )
        return cart

    @staticmethod
    def find_abandoned_cart_for_conversion(
        order_form_id: str, project: Project
    ) -> Optional[Cart]:
        """
        Find an abandoned cart eligible for conversion tracking.

        Searches for carts that:
        1. Match the given order_form_id and project
        2. Have integrated_agent set
        3. Have notification_sent_at set
        4. Have capi_notification_sent=False
        """
        cart = Cart.objects.filter(
            order_form_id=order_form_id,
            project=project,
            integrated_agent__isnull=False,
            notification_sent_at__isnull=False,
            capi_notification_sent=False,
        ).first()

        if cart:
            logger.info(
                f"Abandoned cart eligible for conversion found: "
                f"cart_uuid={cart.uuid} order_form_id={order_form_id} "
                f"project={project.uuid} notification_sent_at={cart.notification_sent_at}"
            )
        else:
            logger.debug(
                f"No abandoned cart eligible for conversion: "
                f"order_form_id={order_form_id} project={project.uuid}"
            )

        return cart
