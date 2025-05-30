import logging

from rest_framework.exceptions import ValidationError

from celery import shared_task
from retail.agents.usecases.order_status_update import AgentOrderStatusUpdateUsecase
from retail.agents.utils import get_integrated_agent_if_exists
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


@shared_task
def task_order_status_update(order_update_data: dict):
    """
    Task to process an order status update.
    """
    try:
        order_status_dto = OrderStatusDTO(**order_update_data)

        integrated_agent = get_integrated_agent_if_exists(order_status_dto.vtexAccount)

        # TODO: extract project validation from OrderStatusUseCase before calling the usecase
        if integrated_agent:
            use_case = AgentOrderStatusUpdateUsecase(integrated_agent)
            use_case.execute(order_status_dto)
        else:
            use_case = OrderStatusUseCase(order_status_dto)
            use_case.process_notification()

        logger.info(
            f"Successfully processed order update for order ID: {order_update_data.get('orderId')}"
        )
    except ValidationError:
        pass
    except Exception as e:
        logger.error(f"Unexpected error processing order update: {str(e)}")
