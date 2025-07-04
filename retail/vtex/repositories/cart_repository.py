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
        Retrieve a cart by its VTEX order-form identifier.

        Args:
            order_form_id: The VTEX order-form ID.
            project: The project instance.
        Returns:
            The matching :class:`Cart` instance or ``None`` if not found.
        """
        return Cart.objects.filter(order_form_id=order_form_id, project=project).first()

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
