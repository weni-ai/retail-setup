import logging

from typing import Dict, Any, Optional

from django.core.cache import cache
from django.conf import settings
from django.forms import ValidationError

from retail.agents.models import IntegratedAgent
from retail.agents.usecases.agent_webhook import (
    AgentWebhookUseCase,
)
from retail.agents.utils import adapt_order_status_to_webhook_payload
from retail.interfaces.clients.aws_lambda.client import RequestData
from retail.projects.models import Project
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


logger = logging.getLogger(__name__)


class AgentOrderStatusUpdateUsecase:
    def get_integrated_agent_if_exists(
        self, project: Project
    ) -> Optional[IntegratedAgent]:
        """
        Retrieve the integrated agent if it exists, with caching for 6 hours.

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
            integrated_agent = IntegratedAgent.objects.get(
                agent__uuid=settings.ORDER_STATUS_AGENT_UUID,
                project=project,
                is_active=True,
            ).exclude(uuid="d30bcce8-ce67-4677-8a33-c12b62a51d4f")
            cache.set(cache_key, integrated_agent, timeout=21600)  # 6 hours
        except IntegratedAgent.DoesNotExist:
            logger.info(
                f"No active integrated agent found for ORDER_STATUS_AGENT_UUID: {settings.ORDER_STATUS_AGENT_UUID}"
            )
            return None

        return integrated_agent

    def get_project_by_vtex_account(self, vtex_account: str) -> Project:
        """
        Get the project by VTEX account, with caching.

        Raises:
            ValidationError: If no project is found or if multiple projects are found.

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
            error_message = (
                f"Project not found for VTEX account {vtex_account}. "
                f"Order id: {self.data.orderId}"
            )
            raise ValidationError(error_message)
        except Project.MultipleObjectsReturned:
            error_message = (
                f"Multiple projects found for VTEX account {vtex_account}. "
                f"Order id: {self.data.orderId}"
            )
            logger.error(error_message)
            raise ValidationError(error_message)

    def execute(
        self, integrated_agent: IntegratedAgent, order_status_dto: OrderStatusDTO
    ) -> None:
        webhook_payload: Dict[str, Any] = adapt_order_status_to_webhook_payload(
            order_status_dto
        )
        request_data = RequestData(
            params={},
            payload=webhook_payload,
        )

        agent_webhook_use_case = AgentWebhookUseCase()
        credentials = agent_webhook_use_case._addapt_credentials(integrated_agent)

        request_data.set_credentials(credentials)
        request_data.set_ignored_official_rules(integrated_agent.ignore_templates)

        agent_webhook_use_case.execute(integrated_agent, request_data)
