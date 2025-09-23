import logging

from typing import Dict, Any, Optional

from django.core.cache import cache
from django.conf import settings
from rest_framework.exceptions import ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
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


class AgentOrderStatusUpdateUsecase:
    def get_integrated_agent_if_exists(
        self, project: Project
    ) -> Optional[IntegratedAgent]:
        """
        Retrieve the integrated agent if it exists, with caching for 6 hours.

        First tries to find the official agent, then looks for custom agents
        that have the official agent as parent_agent_uuid.

        Args:
            project (Project): The project instance.

        Returns:
            Optional[IntegratedAgent]: The integrated agent if found, otherwise None.
        """
        if not settings.ORDER_STATUS_AGENT_UUID:
            logger.warning("ORDER_STATUS_AGENT_UUID is not set in settings.")
            return None

        cache_key = (
            f"integrated_agent_{settings.ORDER_STATUS_AGENT_UUID}_{str(project.uuid)}"
        )
        integrated_agent = cache.get(cache_key)

        if integrated_agent:
            return integrated_agent

        try:
            # First try to find the official agent
            integrated_agent = IntegratedAgent.objects.get(
                agent__uuid=settings.ORDER_STATUS_AGENT_UUID,
                project=project,
                is_active=True,
            )
            logger.info(
                f"Found official integrated agent for ORDER_STATUS_AGENT_UUID: {settings.ORDER_STATUS_AGENT_UUID}"
            )
        except IntegratedAgent.DoesNotExist:
            logger.info(
                f"No official integrated agent found for ORDER_STATUS_AGENT_UUID: {settings.ORDER_STATUS_AGENT_UUID}. "
                f"Looking for agents with parent_agent_uuid filled..."
            )

            # If official agent not found, look for any agent with parent_agent_uuid filled
            try:
                integrated_agent = IntegratedAgent.objects.get(
                    parent_agent_uuid__isnull=False,
                    project=project,
                    is_active=True,
                )
                logger.info(
                    f"Found integrated agent with parent_agent_uuid: {integrated_agent.parent_agent_uuid}"
                )
            except IntegratedAgent.DoesNotExist:
                logger.info(
                    f"No integrated agent found (official or with parent_agent_uuid) for project {project.uuid}"
                )
                return None
            except IntegratedAgent.MultipleObjectsReturned:
                logger.error(
                    f"Multiple agents found with parent_agent_uuid for project {project.uuid}. "
                    f"This should not happen - only one agent per project should have parent_agent_uuid."
                )
                raise ValidationError(
                    {
                        "error": "Multiple agents with parent_agent_uuid found for this project"
                    },
                    code="multiple_parent_agents",
                )

        cache.set(cache_key, integrated_agent, timeout=21600)  # 6 hours
        return integrated_agent

    def get_project_by_vtex_account(self, vtex_account: str) -> Project:
        """
        Get the project by VTEX account, with caching.

        Returns:
            Project: The project associated with the VTEX account.
        """
        cache_key = f"project_by_vtex_account_{vtex_account}"
        project = cache.get(cache_key)

        if project:
            return project

        try:
            project = Project.objects.get(vtex_account=vtex_account)
            cache.set(cache_key, project, timeout=43200)  # 12 hours
            return project
        except Project.DoesNotExist:
            logger.info(f"Project not found for VTEX account {vtex_account}.")
            return None
        except Project.MultipleObjectsReturned:
            logger.error(
                f"Multiple projects found for VTEX account {vtex_account}.",
                exc_info=True,
            )
            return None

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
