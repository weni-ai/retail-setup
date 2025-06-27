"""
Use case for registering (or attaching) a WhatsApp click-ID to a VTEX
order-form stored in the Cart model.
"""

from typing import Optional, TYPE_CHECKING

from retail.vtex.dtos.register_order_form_click_dto import RegisterOrderFormClickDTO
from retail.vtex.repositories.cart_repository import CartRepository


if TYPE_CHECKING:  # only for static type checking
    from ..models import Cart


class RegisterOrderFormClickUseCase:
    """Link a WhatsApp click-ID to the corresponding cart."""

    def __init__(self, repository: Optional[CartRepository] = None) -> None:
        """
        Initialize the use case.

        Args:
            repository: Concrete implementation responsible for persistence.
        """
        self._repo: CartRepository = repository or CartRepository()

    def execute(self, dto: RegisterOrderFormClickDTO) -> "Cart":
        """
        Perform the registration and return the affected cart.

        The operation is idempotent.

        Args:
            dto: Immutable data required by the use case.

        Returns:
            The persisted :class:`Cart` instance.

        Raises:
            ValueError: If the click-ID is already linked to another cart.
        """
        self._ensure_click_is_unique(dto.whatsapp_click_id)

        cart = self._repo.find_by_order_form(dto.order_form_id)
        if cart is None:
            cart = self._repo.create(
                order_form_id=dto.order_form_id,
                whatsapp_click_id=dto.whatsapp_click_id,
            )
        elif cart.whatsapp_click_id != dto.whatsapp_click_id:
            cart.whatsapp_click_id = dto.whatsapp_click_id
            cart = self._repo.save(cart)

        return cart

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #
    def _ensure_click_is_unique(self, click_id: str) -> None:
        """
        Ensure no other cart is using the same click-ID.

        Args:
            click_id: The Meta click-ID coming from WhatsApp.

        Raises:
            ValueError: If the click-ID is already present in another cart.
        """
        existing = self._repo.find_by_click_id(click_id)
        if existing is not None:
            raise ValueError(
                f"Click-ID '{click_id}' is already linked to cart {existing.uuid}."
            )
