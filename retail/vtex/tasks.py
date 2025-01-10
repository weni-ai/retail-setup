from celery import shared_task
from retail.vtex.usecases.cart_abandonment import CartAbandonmentUseCase


@shared_task
def mark_cart_as_abandoned(cart_uuid: str, store: str):
    """
    Mark a cart as abandoned and trigger the broadcast notification process.

    Args:
        cart_uuid (str): The UUID of the cart to process.
    """
    use_case = CartAbandonmentUseCase()
    use_case.process_abandoned_cart(cart_uuid, store)
