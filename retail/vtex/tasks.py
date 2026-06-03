import logging

from datetime import timedelta
from typing import Optional

from django.utils import timezone

from celery import shared_task
from retail.agents.domains.agent_webhook.usecases.webhook import AgentWebhookUseCase
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.agents.domains.agent_execution.task_helpers import execution_log_scope
from retail.broadcasts.usecases.mark_broadcast_converted import (
    MarkBroadcastConvertedUseCase,
)
from retail.vtex.models import Cart
from retail.vtex.usecases.cart_abandonment import CartAbandonmentUseCase
from retail.vtex.usecases.handle_purchase_event import HandlePurchaseEventUseCase
from retail.webhooks.vtex.usecases.order_status import OrderStatusUseCase
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO

from retail.agents.domains.agent_webhook.usecases.abandoned_cart import (
    AgentAbandonedCartUseCase,
)


logger = logging.getLogger(__name__)


# VTEX states that confirm a finalized purchase. Kept in sync with
# ``PURCHASED_ORDER_STATUSES`` in services_cart_abandonment_unified.py
# so the conversion trigger and the abandonment filter speak the same
# language.
_PURCHASE_CONFIRMED_STATES = frozenset({"invoiced"})


@shared_task
def task_abandoned_cart_update(cart_uuid: str):
    """Process an abandoned cart update.

    Wrapped in ``execution_log_scope`` so any failure inside the body
    that already opened an AgentExecution row finalises it as
    ``error`` instead of leaving it in ``processing`` until the ZSET
    deadline expires.
    """
    try:
        cart = Cart.objects.get(uuid=cart_uuid, status="created")
    except Cart.DoesNotExist:
        logger.warning(
            f"[CART_TASK] Cart not found or already processed: cart_uuid={cart_uuid} "
            f"reason=cart_does_not_exist_or_status_changed"
        )
        return

    with execution_log_scope(
        error_data={"cart_uuid": cart_uuid},
        log_prefix="[CART_TASK]",
    ) as exec_logger:
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
            execution_uuid = exec_logger.log_webhook_received(
                integrated_agent=integrated_agent,
                payload={
                    "cart_uuid": cart_uuid,
                    "order_form_id": cart.order_form_id,
                    "phone_number": cart.phone_number,
                },
                contact_urn=f"whatsapp:{cart.phone_number}",
                order_id=cart.order_form_id,
            )

            logger.info(
                f"[CART_TASK] Using agent flow: {log_context} "
                f"agent_uuid={integrated_agent.uuid}"
            )
            use_case.execute(cart, integrated_agent, execution_uuid=execution_uuid)
        elif cart.integrated_feature:
            logger.info(
                f"[CART_TASK] Using feature flow (legacy): {log_context} "
                f"feature_uuid={cart.integrated_feature.uuid}"
            )
            CartAbandonmentUseCase().execute(cart)
        else:
            logger.warning(
                f"[CART_TASK] No integration configured: {log_context} "
                f"reason=no_agent_or_feature_configured"
            )
            return

        logger.info(f"[CART_TASK] Completed abandoned cart processing: {log_context}")


@shared_task
def task_order_status_update(order_update_data: dict):
    """Process an order status update.

    ``ValidationError`` is intentionally swallowed (no re-raise) so a
    bad payload doesn't trigger beat retries — the scope still
    finalises the active execution row as ``error`` first.
    """
    with execution_log_scope(
        error_data={"order_update_data": order_update_data},
        log_prefix="[ORDER_STATUS]",
    ) as exec_logger:
        order_status_dto = OrderStatusDTO(**order_update_data)
        vtex_account = order_status_dto.vtexAccount
        order_id = order_status_dto.orderId
        current_state = order_status_dto.currentState

        logger.info(
            f"[ORDER_STATUS] received: "
            f"vtex_account={vtex_account} data={order_update_data}"
        )

        use_case = AgentOrderStatusUpdateUsecase(exec_logger=exec_logger)
        project = use_case.get_project_by_vtex_account(vtex_account)
        if not project:
            logger.info(
                f"[ORDER_STATUS] project_not_found: vtex_account={vtex_account}"
            )
            return

        if is_payment_approved(current_state):
            logger.info(
                f"[ORDER_STATUS] dispatching_purchase_event: "
                f"vtex_account={vtex_account} current_state={current_state} "
                f"order_id={order_id}"
            )
            handle_purchase_event_task.apply_async(
                args=[order_id, str(project.uuid)],
                queue="vtex-io-orders-update-events",
            )

        if _is_purchase_confirmed(current_state):
            logger.info(
                f"[CONVERSION_TRACKING] dispatching_conversion_check: "
                f"vtex_account={vtex_account} current_state={current_state} "
                f"order_id={order_id}"
            )
            task_mark_broadcast_converted.apply_async(
                args=[order_id, str(project.uuid)],
                queue="vtex-io-orders-update-events",
            )

        integrated_agent = use_case.get_integrated_agent_if_exists(project)

        if integrated_agent:
            exec_logger.log_webhook_received(
                integrated_agent=integrated_agent,
                payload=order_update_data,
                order_id=order_status_dto.orderId,
            )

            logger.info(
                f"[ORDER_STATUS] processing_with_agent: "
                f"vtex_account={vtex_account} current_state={current_state} "
                f"order_id={order_id} agent_uuid={integrated_agent.uuid}"
            )
            use_case.execute(integrated_agent, order_status_dto)
        else:
            logger.info(
                f"[ORDER_STATUS] processing_with_legacy: "
                f"vtex_account={vtex_account} current_state={current_state} "
                f"order_id={order_id}"
            )
            OrderStatusUseCase(order_status_dto).process_notification(project)

        logger.info(
            f"[ORDER_STATUS] completed: "
            f"vtex_account={vtex_account} current_state={current_state} "
            f"order_id={order_id}"
        )


def is_payment_approved(order_status: str) -> bool:
    return order_status in {"payment-approved"}


def _is_purchase_confirmed(order_status: str) -> bool:
    """Return True when the VTEX state confirms a finalized purchase.

    Mirrors the ``PURCHASED_ORDER_STATUSES`` set used by the cart
    abandonment service, kept here as a private helper so the
    conversion trigger does not depend on the abandonment service
    module.
    """
    return order_status in _PURCHASE_CONFIRMED_STATES


@shared_task
def task_agent_webhook(
    integrated_agent_uuid: str,
    payload: dict,
    params: dict,
    execution_uuid: Optional[str] = None,
):
    """Process an agent webhook.

    Thin glue: delegates the resolve-agent / forward-UUID / dispatch
    flow to :meth:`AgentWebhookUseCase.execute_from_task` so the task
    holds no business logic. ``execution_uuid`` is forwarded by inner
    callers (e.g. ``task_abandoned_cart_update``) so a single
    AgentExecution row covers the whole chain.
    """
    with execution_log_scope(
        error_data={"integrated_agent_uuid": integrated_agent_uuid},
        log_prefix="[AGENT_WEBHOOK]",
    ) as exec_logger:
        logger.info(
            f"Processing agent webhook. "
            f"Integrated Agent: {integrated_agent_uuid}, "
            f"Payload: {payload}, params: {params}"
        )

        return AgentWebhookUseCase(exec_logger=exec_logger).execute_from_task(
            integrated_agent_uuid=integrated_agent_uuid,
            payload=payload,
            params=params,
            forwarded_execution_uuid=execution_uuid,
        )


@shared_task
def handle_purchase_event_task(order_id: str, project_uuid: str):
    use_case = HandlePurchaseEventUseCase()
    use_case.execute(order_id=order_id, project_uuid=project_uuid)


@shared_task
def task_mark_broadcast_converted(order_id: str, project_uuid: str):
    """Attribute an ``invoiced`` VTEX order to the broadcast that drove it.

    Isolated from ``task_order_status_update`` so a transient VTEX I/O
    failure on the conversion lookup retries on its own without
    re-triggering the agent webhook flow that already ran.
    """
    use_case = MarkBroadcastConvertedUseCase()
    use_case.execute(order_id=order_id, project_uuid=project_uuid)


@shared_task
def task_notify_lead(lead_uuid: str):
    """Send Slack Block Kit notification for a new or updated lead."""
    from retail.vtex.models import Lead
    from retail.services.notification.service import LeadNotificationService

    try:
        lead = Lead.objects.get(uuid=lead_uuid)

        brazil_tz = timezone.get_fixed_timezone(-180)
        local_date = lead.modified_on.astimezone(brazil_tz)

        lead_data = {
            "user_email": lead.user_email,
            "vtex_account": lead.vtex_account,
            "plan": lead.plan,
            "region": lead.region,
            "date": local_date.strftime("%Y-%m-%d %H:%M"),
            "data": lead.data,
        }

        LeadNotificationService().notify(lead_data)

        logger.info(
            f"Lead Slack notification sent for " f"vtex_account={lead.vtex_account}"
        )
    except Lead.DoesNotExist:
        logger.error(f"Lead not found: uuid={lead_uuid}")
    except Exception as e:
        logger.error(
            f"Failed to send lead notification: " f"lead_uuid={lead_uuid} error={e}",
            exc_info=True,
        )


@shared_task(name="task_cleanup_old_carts")
def task_cleanup_old_carts():
    try:
        time_threshold = timezone.now() - timedelta(days=15)
        Cart.objects.filter(created_on__lt=time_threshold).delete()

        logger.info("Old cart records have been cleaned up.")
    except Exception as e:
        logger.error(f"Error cleaning up old cart records: {str(e)}", exc_info=True)
