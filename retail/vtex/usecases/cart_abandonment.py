import logging

from retail.vtex.models import Cart
from retail.vtex.usecases.base import BaseVtexUseCase
from retail.webhooks.vtex.services_cart_abandonment_unified import (
    CartAbandonmentService,
)

logger = logging.getLogger(__name__)


class CartAbandonmentUseCase(BaseVtexUseCase):
    """
    Use case for handling cart abandonment and notifications.
    Now uses the unified CartAbandonmentService as the single source of truth.
    """

    def __init__(self):
        """
        Initialize the CartAbandonmentUseCase with the unified service.
        """
        self.cart_abandonment_service = CartAbandonmentService()

    def execute(self, cart: Cart):
        """
        Process a cart marked as abandoned.
        Now delegates to the unified CartAbandonmentService.

        Args:
            cart (Cart): The cart to process.
        """

        # Use the unified service to process the cart
        self.cart_abandonment_service.process_abandoned_cart(
            cart=cart, integration_config=cart.integrated_feature
        )
