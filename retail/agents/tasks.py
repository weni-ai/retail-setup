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
            f"Processing delivered order tracking webhook task for agent {integrated_agent_uuid}"
        )

        # Initialize use case
        webhook_use_case = DeliveredOrderTrackingWebhookUseCase()

        # Get integrated agent
        integrated_agent = webhook_use_case.get_integrated_agent(integrated_agent_uuid)

        # Process webhook notification
        result = webhook_use_case.process_webhook_notification(
            integrated_agent, webhook_data
        )

        logger.info(
            f"Successfully processed delivered order tracking webhook for agent {integrated_agent_uuid}: {result}"
        )

    except Exception as e:
        logger.exception(
            f"Error processing delivered order tracking webhook task for agent {integrated_agent_uuid}: {e}"
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
            f"Processing payment recovery webhook task for agent {integrated_agent_uuid}"
        )

        use_case = PaymentRecoveryWebhookUseCase()
        integrated_agent = use_case.get_integrated_agent(integrated_agent_uuid)
        result = use_case.process_webhook_notification(integrated_agent, webhook_data)

        logger.info(
            f"Successfully processed payment recovery webhook for "
            f"agent {integrated_agent_uuid}: {result}"
        )

    except Exception as e:
        logger.exception(
            f"Error processing payment recovery webhook task for "
            f"agent {integrated_agent_uuid}: {e}"
        )
