import logging

from rest_framework.exceptions import ValidationError

from celery import shared_task
from retail.vtex.usecases.cart_abandonment import CartAbandonmentUseCase
from retail.webhooks.vtex.usecases.order_status import OrderStatusUseCase
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


logger = logging.getLogger(__name__)


@shared_task
def mark_cart_as_abandoned(cart_uuid: str):
    """
    Mark a cart as abandoned and trigger the broadcast notification process.

    Args:
        cart_uuid (str): The UUID of the cart to process.
    """
    use_case = CartAbandonmentUseCase()
    use_case.process_abandoned_cart(cart_uuid)


@shared_task(bind=True)
def task_order_status_update(self, order_update_data: dict):
    """
    Task to process an order status update.
    """
    try:
        order_status_dto = OrderStatusDTO(**order_update_data)
        use_case = OrderStatusUseCase(order_status_dto)
        use_case.process_notification()
        logger.info(
            f"Successfully processed order update for order ID: {order_update_data.get('orderId')}"
        )
    except ValidationError as e:
        logger.error(f"Validation error processing order update: {str(e)}")
        raise self.retry(exc=e, countdown=60, max_retries=1)
    except Exception as e:
        logger.error(f"Unexpected error processing order update: {str(e)}")
        raise self.retry(exc=e, countdown=60, max_retries=1)
