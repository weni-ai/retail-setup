import logging

from typing import Optional
from uuid import UUID

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
