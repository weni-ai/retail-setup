from typing import Optional
from ..models import Cart


class CartRepository:
    """Abstraction over Cart persistence."""

    @staticmethod
    def find_by_order_form(order_form_id: str) -> Optional[Cart]:
        """
        Retrieve a cart by its VTEX order-form identifier.

        Args:
            order_form_id: The VTEX order-form ID.

        Returns:
            The matching :class:`Cart` instance or ``None`` if not found.
        """
        return Cart.objects.filter(order_form_id=order_form_id).first()

    @staticmethod
    def find_by_click_id(click_id: str) -> Optional[Cart]:
        """
        Retrieve a cart by its WhatsApp click identifier.

        Args:
            click_id: The Meta click-ID.

        Returns:
            The matching :class:`Cart` instance or ``None`` if not found.
        """
        return Cart.objects.filter(whatsapp_click_id=click_id).first()

    @staticmethod
    def save(cart: Cart) -> Cart:
        """
        Persist the cart instance.

        Uses ``update_fields`` when the object already exists to
        avoid Django's ``ValueError`` during INSERT.

        Args:
            cart: The cart entity to be persisted.

        Returns:
            The saved :class:`Cart` instance.
        """
        if cart.pk:
            cart.save(update_fields=["whatsapp_click_id", "modified_on"])
        else:
            cart.save()
        return cart

    @staticmethod
    def create(order_form_id: str, whatsapp_click_id: str) -> Cart:
        """
        Create and persist a new cart with the required fields.

        Args:
            order_form_id: The VTEX order-form ID.
            whatsapp_click_id: The Meta click-ID.

        Returns:
            The newly created :class:`Cart` instance.
        """
        return Cart.objects.create(
            order_form_id=order_form_id,
            whatsapp_click_id=whatsapp_click_id,
        )
