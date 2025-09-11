import logging

from typing import Optional

from django.conf import settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.usecases.base_agent_webhook import (
    BaseAgentWebhookUseCase,
)
from retail.projects.models import Project
from retail.vtex.models import Cart

from retail.webhooks.vtex.services_cart_abandonment_unified import (
    CartAbandonmentService,
)
from retail.services.vtex_io.service import VtexIOService
from retail.clients.vtex_io.client import VtexIOClient


logger = logging.getLogger(__name__)


class AgentAbandonedCartUseCase(BaseAgentWebhookUseCase):
    """
    Use case for handling abandoned cart notifications via integrated agent.
    Now uses the unified CartAbandonmentService as the single source of truth.
    """

    def __init__(self):
        super().__init__()
        self.cart_abandonment_service = CartAbandonmentService()
        self.vtex_io_service = VtexIOService(VtexIOClient())

    def get_integrated_agent(self, project: Project) -> Optional[IntegratedAgent]:
        """
        Retrieve the integrated agent if it exists.

        Args:
            project (Project): The project instance.

        Returns:
            Optional[IntegratedAgent]: The integrated agent if found, None otherwise.
        """
        integrated_agent = self.get_integrated_agent_if_exists(
            project, settings.ABANDONED_CART_AGENT_UUID
        )

        return integrated_agent

    def execute(self, cart: Cart, integrated_agent: IntegratedAgent) -> None:
        """
        Execute the abandoned cart agent webhook process.
        Now delegates to the unified CartAbandonmentService.

        Args:
            cart (Cart): The abandoned cart instance.
            integrated_agent (IntegratedAgent): The integrated agent to execute.
        """
        try:
            logger.info(
                f"Starting execution for integrated agent: {integrated_agent.uuid} "
                f"and cart ID: {cart.uuid}"
            )

            # Use the unified service to process the cart
            self.cart_abandonment_service.process_abandoned_cart(
                cart=cart, integration_config=integrated_agent
            )

            logger.info(
                f"Execution completed for integrated agent: {integrated_agent.uuid} "
                f"and cart ID: {cart.uuid}"
            )
        except Exception as e:
            logger.exception(
                f"Unexpected error while processing cart {cart.uuid}: {str(e)}"
            )
