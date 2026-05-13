import logging

from datetime import timedelta
from typing import Optional
from uuid import UUID

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from celery import shared_task
from retail.agents.domains.agent_webhook.usecases.webhook import AgentWebhookUseCase
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.agents.domains.agent_execution.context import set_current_execution_uuid
from retail.agents.domains.agent_execution.services.logger import ExecutionLoggerService
from retail.broadcasts.usecases.mark_broadcast_converted import (
    MarkBroadcastConvertedUseCase,
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


# VTEX states that confirm a finalized purchase. Kept in sync with
# ``PURCHASED_ORDER_STATUSES`` in services_cart_abandonment_unified.py
# so the conversion trigger and the abandonment filter speak the same
# language.
_PURCHASE_CONFIRMED_STATES = frozenset({"invoiced"})


@shared_task
def task_abandoned_cart_update(cart_uuid: str):
    """
    Task to process an abandoned cart update.
    """
    execution_uuid: Optional[UUID] = None
    # Tasks are the composition root for ExecutionLoggerService:
    # instantiate here and inject into use cases via constructor.
    exec_logger = ExecutionLoggerService()

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
            # Start execution logging for abandoned cart agent
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
        # Log error if we have an execution_uuid
        if execution_uuid:
            exec_logger.log_execution_error(
                execution_uuid=execution_uuid,
                error_message=str(e),
                error_data={"cart_uuid": cart_uuid},
            )
        logger.error(
            f"[CART_TASK] Unexpected error: cart_uuid={cart_uuid} error={str(e)}",
            exc_info=True,
        )


@shared_task
def task_order_status_update(order_update_data: dict):
    """
    Task to process an order status update.
    """
    execution_uuid: Optional[UUID] = None
    exec_logger = ExecutionLoggerService()

    try:
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
            # Start execution logging for order status agent
            execution_uuid = exec_logger.log_webhook_received(
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
            legacy_use_case = OrderStatusUseCase(order_status_dto)
            legacy_use_case.process_notification(project)

        logger.info(
            f"[ORDER_STATUS] completed: "
            f"vtex_account={vtex_account} current_state={current_state} "
            f"order_id={order_id}"
        )
    except ValidationError as e:
        # Swallow ValidationError to preserve existing beat-driven retry
        # semantics, but surface it as a terminal error trace if we
        # already opened an execution log; otherwise the row would
        # linger at `processing` until the ZSET deadline.
        if execution_uuid:
            exec_logger.log_execution_error(
                execution_uuid=execution_uuid,
                error_message=f"Validation error: {str(e)}",
                error_data={"order_update_data": order_update_data},
            )
    except Exception as e:
        # Log error if we have an execution_uuid
        if execution_uuid:
            exec_logger.log_execution_error(
                execution_uuid=execution_uuid,
                error_message=str(e),
                error_data={"order_update_data": order_update_data},
            )
        logger.error(
            f"[ORDER_STATUS] unexpected_error: " f"data={order_update_data} error={e}",
            exc_info=True,
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
    """
    Task to process an agent webhook.

    Two callers exist:

    - The async webhook view (``apply_async``) which has no upstream
      execution log. It calls without ``execution_uuid`` and the task
      starts a fresh AgentExecution via ``log_webhook_received``.
    - Inner callers that already opened an execution log earlier in
      the chain (e.g. ``task_abandoned_cart_update``) and pass the UUID
      down. The task reuses it, sets the contextvar, and skips
      ``log_webhook_received`` so a single AgentExecution row covers
      the whole flow.

    Args:
        integrated_agent_uuid: UUID of the integrated agent (as string).
        payload: Webhook payload data.
        params: Query parameters from the webhook.
        execution_uuid: Optional pre-existing AgentExecution UUID, as a
            string. Celery JSON serialization requires strings, not UUID
            objects.
    """
    exec_logger = ExecutionLoggerService()

    logger.info(
        f"Processing agent webhook. "
        f"Integrated Agent: {integrated_agent_uuid}, Payload: {payload}, params: {params}"
    )

    use_case = AgentWebhookUseCase(exec_logger=exec_logger)
    request_data = RequestData(
        params=params,
        payload=payload,
    )

    # When the caller forwarded an execution UUID, an upstream task has
    # already opened a row linked to its (then-resolved) IntegratedAgent.
    # Set the contextvar before the lookup so we can close the row with
    # an explicit skip if the agent has since been deleted/blocked,
    # rather than letting the ZSET deadline force-finalise it as
    # `Execution timed out`. We do NOT open a new row for a missing
    # agent.
    forwarded_uuid: Optional[UUID] = UUID(execution_uuid) if execution_uuid else None
    if forwarded_uuid is not None:
        set_current_execution_uuid(forwarded_uuid)

    integrated_agent = use_case._get_integrated_agent(integrated_agent_uuid)
    if not integrated_agent:
        logger.info(f"Integrated agent not found for UUID {integrated_agent_uuid}.")
        if forwarded_uuid is not None:
            exec_logger.log_execution_skip(
                execution_uuid=forwarded_uuid,
                reason="integrated_agent_missing_or_blocked",
                skip_data={"integrated_agent_uuid": integrated_agent_uuid},
            )
        return

    if forwarded_uuid is not None:
        exec_uuid: UUID = forwarded_uuid
    else:
        exec_uuid = exec_logger.log_webhook_received(
            integrated_agent=integrated_agent,
            payload=payload,
        )

    try:
        credentials = use_case._addapt_credentials(integrated_agent)

        request_data.set_credentials(credentials)
        request_data.set_ignored_official_rules(integrated_agent.ignore_templates)

        return use_case.execute(integrated_agent, request_data)
    except Exception as e:
        exec_logger.log_execution_error(
            execution_uuid=exec_uuid,
            error_message=str(e),
            error_data={"integrated_agent_uuid": integrated_agent_uuid},
        )
        logger.error(
            f"Error processing agent webhook for {integrated_agent_uuid}: {str(e)}",
            exc_info=True,
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
