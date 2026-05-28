import logging

from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from celery import shared_task
from retail.agents.domains.agent_webhook.usecases.webhook import AgentWebhookUseCase
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.broadcasts.usecases.mark_broadcast_converted import (
    MarkBroadcastConvertedUseCase,
)
from retail.interfaces.clients.aws_lambda.client import RequestData
from retail.vtex.models import Cart
from retail.vtex.usecases.cart_abandonment import CartAbandonmentUseCase
from retail.vtex.usecases.handle_abandoned_cart_conversion import (
    HandleAbandonedCartConversionUseCase,
)
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
        vtex_account = order_status_dto.vtexAccount
        order_id = order_status_dto.orderId
        current_state = order_status_dto.currentState

        logger.info(
            f"[ORDER_STATUS] received: "
            f"vtex_account={vtex_account} data={order_update_data}"
        )

        use_case = AgentOrderStatusUpdateUsecase()
        project = use_case.get_project_by_vtex_account(vtex_account)
        if not project:
            logger.info(
                f"[ORDER_STATUS] project_not_found: vtex_account={vtex_account}"
            )
            return

        if is_payment_approved(current_state):
            # TODO(refactor): every payment-approved event currently fans out
            # into N independent tasks, and each one performs its own
            # ``VtexIOService.get_order_details_by_id`` call. As long as we
            # have just two consumers (CAPI + abandoned-cart conversion) the
            # extra HTTP call is acceptable, but adding a third consumer
            # multiplies the cost linearly. The original PR #376 design
            # solved this with a single orchestrator that fetched the order
            # once and shared an ``OrderContext`` with all handlers; revisit
            # that approach (or memoize ``get_order_details_by_id`` per
            # order_id) once a third consumer is on the table.
            logger.info(
                f"[ORDER_STATUS] dispatching_purchase_event: "
                f"vtex_account={vtex_account} current_state={current_state} "
                f"order_id={order_id}"
            )
            handle_purchase_event_task.apply_async(
                args=[order_id, str(project.uuid)],
                queue="vtex-io-orders-update-events",
            )

            logger.info(
                f"[ABANDONED_CART_CONVERSION] dispatching_conversion_check: "
                f"vtex_account={vtex_account} current_state={current_state} "
                f"order_id={order_id}"
            )
            task_handle_abandoned_cart_conversion.apply_async(
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
    except ValidationError:
        pass
    except Exception as e:
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

    return use_case.execute(integrated_agent, request_data)


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
def task_handle_abandoned_cart_conversion(order_id: str, project_uuid: str):
    """Detect and report abandoned-cart-driven conversions to Flows datalake.

    Isolated from ``handle_purchase_event_task`` so a transient VTEX I/O
    failure on the conversion lookup retries on its own without
    re-triggering the purchase-event flow that already ran.
    """
    use_case = HandleAbandonedCartConversionUseCase()
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
