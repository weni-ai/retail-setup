from typing import Dict, Any

from retail.agents.models import IntegratedAgent
from retail.agents.usecases.agent_webhook import AgentWebhookUseCase
from retail.agents.utils import adapt_order_status_to_webhook_payload
from retail.interfaces.clients.aws_lambda.client import RequestData
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


class AgentOrderStatusUpdateUsecase:
    """
    Use case for sending an order status update via an IntegratedAgent (v2.0).

    This use case builds the appropriate webhook payload and dispatches it to
    the webhook endpoint of the associated integrated agent.
    """

    def __init__(self, integrated_agent: IntegratedAgent):
        """
        Initializes the use case with the given integrated agent.

        Args:
            integrated_agent (IntegratedAgent): The agent to which the update will be sent.
        """
        self.integrated_agent = integrated_agent

    def execute(self, order_status_dto: OrderStatusDTO) -> None:
        """
        Builds and sends the order status webhook payload to the integrated agent.

        Args:
            order_status_dto (OrderStatusDTO): DTO containing the order status details.

        Raises:
            ValueError: If the webhook call fails.
        """
        webhook_payload: Dict[str, Any] = adapt_order_status_to_webhook_payload(
            order_status_dto
        )
        request_data = RequestData(
            params={},
            payload=webhook_payload,
        )

        agent_webhook_use_case = AgentWebhookUseCase()
        agent_webhook_use_case.execute(
            self.integrated_agent.uuid, request_data, self.integrated_agent
        )
