import logging

from typing import Dict, Any, Optional

from django.conf import settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.usecases.base_agent_webhook import (
    BaseAgentWebhookUseCase,
)
from retail.agents.domains.agent_webhook.usecases.webhook import (
    AgentWebhookUseCase,
)
from retail.interfaces.clients.aws_lambda.client import RequestData
from retail.projects.models import Project
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


logger = logging.getLogger(__name__)


def adapt_order_status_to_webhook_payload(
    order_status_dto: OrderStatusDTO,
) -> Dict[str, Any]:
    """
    Adapts an OrderStatusDTO instance to a webhook payload format.

    Args:
        order_status_dto (OrderStatusDTO): The DTO with order status information.

    Returns:
        Dict[str, Any]: A dictionary formatted as a webhook payload.
    """
    return {
        "Domain": order_status_dto.domain,
        "OrderId": order_status_dto.orderId,
        "State": order_status_dto.currentState,
        "LastState": order_status_dto.lastState,
        "Origin": {
            "Account": order_status_dto.vtexAccount,
            "Sender": "Gallery",
        },
    }


class AgentOrderStatusUpdateUsecase(BaseAgentWebhookUseCase):
    def get_integrated_agent(self, project: Project) -> Optional[IntegratedAgent]:
        """
        Retrieve the integrated agent if it exists.

        Args:
            project (Project): The project instance.

        Returns:
            Optional[IntegratedAgent]: The integrated agent if found, otherwise None.
        """
        if not settings.ORDER_STATUS_AGENT_UUID:
            logger.warning("ORDER_STATUS_AGENT_UUID is not set in settings.")
            return None

        integrated_agent = self.get_integrated_agent_if_exists(
            project, settings.ORDER_STATUS_AGENT_UUID
        )

        return integrated_agent

    def execute(
        self, integrated_agent: IntegratedAgent, order_status_dto: OrderStatusDTO
    ) -> None:
        logger.info(
            f"Starting execution for integrated agent: {integrated_agent.uuid} "
            f"and order ID: {order_status_dto.orderId}"
        )

        webhook_payload: Dict[str, Any] = adapt_order_status_to_webhook_payload(
            order_status_dto
        )
        logger.info(f"Adapted order status to webhook payload: {webhook_payload}")

        request_data = RequestData(
            params={},
            payload=webhook_payload,
        )

        agent_webhook_use_case = AgentWebhookUseCase()
        credentials = agent_webhook_use_case._addapt_credentials(integrated_agent)

        request_data.set_credentials(credentials)
        request_data.set_ignored_official_rules(integrated_agent.ignore_templates)

        agent_webhook_use_case.execute(integrated_agent, request_data)
        logger.info(
            f"Execution completed for integrated agent: {integrated_agent.uuid} "
            f"and order ID: {order_status_dto.orderId}"
        )
