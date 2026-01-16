import logging

from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from celery import shared_task
from retail.agents.domains.agent_webhook.usecases.webhook import AgentWebhookUseCase
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.interfaces.clients.aws_lambda.client import RequestData
from retail.vtex.models import Cart
from retail.vtex.usecases.cart_abandonment import CartAbandonmentUseCase
from retail.vtex.usecases.handle_purchase_event import HandlePurchaseEventUseCase
from retail.webhooks.vtex.usecases.order_status import OrderStatusUseCase
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO

from retail.agents.domains.agent_webhook.usecases.abandoned_cart import (
    AgentAbandonedCartUseCase,
)


logger = logging.getLogger(__name__)


@shared_task
def task_abandoned_cart_update(cart_uuid: str):
    """
    Task to process an abandoned cart update.
    """
    try:
        # Get the cart to access
        cart = Cart.objects.get(uuid=cart_uuid, status="created")

        # Build log context with all relevant tracking info
        vtex_account = cart.project.vtex_account if cart.project else "unknown"
        project_uuid = str(cart.project.uuid) if cart.project else "unknown"
        log_context = (
            f"vtex_account={vtex_account} cart_uuid={cart_uuid} "
            f"phone={cart.phone_number} project_uuid={project_uuid} "
            f"order_form={cart.order_form_id}"
        )

        logger.info(f"[CART_TASK] Starting abandoned cart processing: {log_context}")

        use_case = AgentAbandonedCartUseCase()
        if not cart.project:
            logger.warning(
                f"[CART_TASK] Project not found: cart_uuid={cart_uuid} "
                f"reason=cart_has_no_project"
            )
            return

        integrated_agent = use_case.get_integrated_agent(cart.project)

        if integrated_agent:
            logger.info(
                f"[CART_TASK] Using agent flow: {log_context} "
                f"agent_uuid={integrated_agent.uuid}"
            )
            use_case.execute(cart, integrated_agent)
        elif cart.integrated_feature:
            logger.info(
                f"[CART_TASK] Using feature flow (legacy): {log_context} "
                f"feature_uuid={cart.integrated_feature.uuid}"
            )
            legacy_use_case = CartAbandonmentUseCase()
            legacy_use_case.execute(cart)
        else:
            logger.warning(
                f"[CART_TASK] No integration configured: {log_context} "
                f"reason=no_agent_or_feature_configured"
            )
            return

        logger.info(f"[CART_TASK] Completed abandoned cart processing: {log_context}")
    except Cart.DoesNotExist:
        logger.warning(
            f"[CART_TASK] Cart not found or already processed: cart_uuid={cart_uuid} "
            f"reason=cart_does_not_exist_or_status_changed"
        )
        return
    except Exception as e:
        logger.error(
            f"[CART_TASK] Unexpected error: cart_uuid={cart_uuid} error={str(e)}",
            exc_info=True,
        )


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
                f"Processing order status with integrated agent. "
                f"VTEX Account: {order_status_dto.vtexAccount}, "
                f"Integrated Agent: {integrated_agent.uuid}, DTO: {order_update_data}"
            )
            use_case.execute(integrated_agent, order_status_dto)
        else:
            logger.info(
                f"Processing order status with legacy use case. "
                f"VTEX Account: {order_status_dto.vtexAccount}, DTO: {order_update_data}"
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
def task_agent_webhook(integrated_agent_uuid: str, payload: dict, params: dict):
    logger.info(
        f"Processing agent webhook. "
        f"Integrated Agent: {integrated_agent_uuid}, Payload: {payload}, params: {params}"
    )

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


@shared_task(name="task_cleanup_old_carts")
def task_cleanup_old_carts():
    try:
        # Delete all Cart records older than 15 days
        time_threshold = timezone.now() - timedelta(days=15)
        Cart.objects.filter(created_on__lt=time_threshold).delete()

        logger.info("Old cart records have been cleaned up.")
    except Exception as e:
        logger.error(f"Error cleaning up old cart records: {str(e)}", exc_info=True)
