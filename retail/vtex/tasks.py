import logging

from rest_framework.exceptions import ValidationError

from celery import shared_task
from retail.agents.usecases.agent_webhook import AgentWebhookUseCase
from retail.agents.usecases.order_status_update import AgentOrderStatusUpdateUsecase
from retail.interfaces.clients.aws_lambda.client import RequestData
from retail.vtex.usecases.cart_abandonment import CartAbandonmentUseCase
from retail.vtex.usecases.handle_purchase_event import HandlePurchaseEventUseCase
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

        use_case = AgentOrderStatusUpdateUsecase()
        project = use_case.get_project_by_vtex_account(order_status_dto.vtexAccount)
        if not project:
            logger.info(
                f"Project not found for VTEX account {order_status_dto.vtexAccount}."
            )
            return

        if is_payment_approved(order_status_dto.currentState):
            logger.info(
                f"Processing purchase event for order ID: {order_status_dto.orderId} "
                f"VTEX account: {order_status_dto.vtexAccount}"
            )
            handle_purchase_event_task.apply_async(
                args=[order_status_dto.orderId, str(project.uuid)],
                queue="vtex-io-orders-update-events",
            )

        integrated_agent = use_case.get_integrated_agent_if_exists(project)

        if integrated_agent:
            logger.info(
                f"Use integrated agent for VTEX account {order_status_dto.vtexAccount}."
            )
            use_case.execute(integrated_agent, order_status_dto)
        else:
            logger.info(
                f"Use legacy use case for VTEX account {order_status_dto.vtexAccount}."
            )
            legacy_use_case = OrderStatusUseCase(order_status_dto)
            legacy_use_case.process_notification(project)

        logger.info(
            f"Successfully processed order update for order ID: {order_update_data.get('orderId')} "
            f"VTEX account: {order_status_dto.vtexAccount}"
        )
    except ValidationError:
        pass
    except Exception as e:
        logger.error(
            f"Unexpected error processing order update: {str(e)}", exc_info=True
        )


def is_payment_approved(order_status: str) -> bool:
    return order_status in {"payment-approved"}


@shared_task
def task_order_status_agent_webhook(
    integrated_agent_uuid: str, payload: dict, params: dict
):
    use_case = AgentWebhookUseCase()
    request_data = RequestData(
        params=params,
        payload=payload,
    )
    integrated_agent = use_case._get_integrated_agent(integrated_agent_uuid)
    if not integrated_agent:
        logger.info(f"Integrated agent not found for UUID {integrated_agent_uuid}.")
        return

    credentials = use_case._addapt_credentials(integrated_agent)

    request_data.set_credentials(credentials)
    request_data.set_ignored_official_rules(integrated_agent.ignore_templates)

    use_case.execute(integrated_agent, request_data)


@shared_task
def handle_purchase_event_task(order_id: str, project_uuid: str):
    use_case = HandlePurchaseEventUseCase()
    use_case.execute(order_id=order_id, project_uuid=project_uuid)
