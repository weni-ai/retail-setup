import logging
from typing import Dict, Any

from celery import shared_task

from retail.agents.domains.agent_integration.usecases.delivered_order_tracking import (
    DeliveredOrderTrackingWebhookUseCase,
)
from retail.agents.domains.agent_integration.usecases.payment_recovery import (
    PaymentRecoveryWebhookUseCase,
)


logger = logging.getLogger(__name__)


@shared_task
def task_delivered_order_tracking_webhook(
    integrated_agent_uuid: str, webhook_data: Dict[str, Any]
) -> None:
    """
    Process delivered order tracking webhook notification asynchronously.

    Args:
        integrated_agent_uuid: UUID of the integrated agent
        webhook_data: Data received from VTEX webhook
    """
    try:
        logger.info(
            f"[DELIVERED_TRACKING] task_started: "
            f"agent_uuid={integrated_agent_uuid} data={webhook_data}"
        )

        webhook_use_case = DeliveredOrderTrackingWebhookUseCase()
        integrated_agent = webhook_use_case.get_integrated_agent(integrated_agent_uuid)
        vtex_account = integrated_agent.project.vtex_account

        result = webhook_use_case.process_webhook_notification(
            integrated_agent, webhook_data
        )

        logger.info(
            f"[DELIVERED_TRACKING] task_completed: "
            f"vtex_account={vtex_account} agent_uuid={integrated_agent_uuid} "
            f"result={result} data={webhook_data}"
        )

    except Exception as e:
        logger.exception(
            f"[DELIVERED_TRACKING] task_failed: "
            f"agent_uuid={integrated_agent_uuid} "
            f"data={webhook_data} error={e}"
        )


@shared_task
def task_payment_recovery_webhook(
    integrated_agent_uuid: str, webhook_data: Dict[str, Any]
) -> None:
    """
    Process payment recovery webhook notification asynchronously.

    Args:
        integrated_agent_uuid: UUID of the integrated agent
        webhook_data: Data received from VTEX webhook
    """
    try:
        logger.info(
            f"[PAYMENT_RECOVERY] task_started: "
            f"agent_uuid={integrated_agent_uuid} data={webhook_data}"
        )

        use_case = PaymentRecoveryWebhookUseCase()
        integrated_agent = use_case.get_integrated_agent(integrated_agent_uuid)
        vtex_account = integrated_agent.project.vtex_account

        result = use_case.process_webhook_notification(integrated_agent, webhook_data)

        logger.info(
            f"[PAYMENT_RECOVERY] task_completed: "
            f"vtex_account={vtex_account} agent_uuid={integrated_agent_uuid} "
            f"result={result} data={webhook_data}"
        )

    except Exception as e:
        logger.exception(
            f"[PAYMENT_RECOVERY] task_failed: "
            f"agent_uuid={integrated_agent_uuid} "
            f"data={webhook_data} error={e}"
        )
