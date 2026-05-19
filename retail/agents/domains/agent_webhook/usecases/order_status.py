import logging

from typing import Dict, Any, Optional

from django.core.cache import cache
from django.conf import settings
from rest_framework.exceptions import ValidationError

from retail.agents.domains.agent_execution.services.logger import ExecutionLoggerService
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.usecases.webhook import (
    AgentWebhookUseCase,
)
from retail.agents.shared.cache import (
    AgentRole,
    IntegratedAgentCacheHandler,
    IntegratedAgentCacheHandlerRedis,
)
from retail.interfaces.clients.aws_lambda.client import RequestData
from retail.interfaces.services.execution_logger import (
    ExecutionLoggerServiceInterface,
)
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
            "Sender": "order-status-api",
        },
    }


class AgentOrderStatusUpdateUsecase:
    def __init__(
        self,
        cache_handler: Optional[IntegratedAgentCacheHandler] = None,
        exec_logger: Optional[ExecutionLoggerServiceInterface] = None,
    ) -> None:
        self.cache_handler = cache_handler or IntegratedAgentCacheHandlerRedis()
        self.exec_logger: ExecutionLoggerServiceInterface = (
            exec_logger or ExecutionLoggerService()
        )

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
            logger.warning(
                f"[ORDER_STATUS] agent_uuid_not_set: "
                f"vtex_account={project.vtex_account} project_uuid={project.uuid}"
            )
            return None

        cached = self.cache_handler.get_role_agent(project.uuid, AgentRole.ORDER_STATUS)
        if cached is not None:
            return cached

        integrated_agent = self._lookup_order_status_agent(project)
        if integrated_agent is None:
            return None

        self.cache_handler.set_role_agent(integrated_agent, AgentRole.ORDER_STATUS)
        return integrated_agent

    def _lookup_order_status_agent(self, project: Project) -> Optional[IntegratedAgent]:
        """Resolve the order-status agent for ``project`` from the database.

        Tries the official agent first; only when ``DoesNotExist`` is
        raised, falls back to any custom agent flagged with
        ``parent_agent_uuid`` (inherited order-status logic). The
        nested structure mirrors that "fallback only on missing
        official" intent visually.
        """
        try:
            integrated_agent = IntegratedAgent.objects.get(
                agent__uuid=settings.ORDER_STATUS_AGENT_UUID,
                project=project,
                is_active=True,
            )
            logger.info(
                f"[ORDER_STATUS] agent_resolved: "
                f"vtex_account={project.vtex_account} "
                f"agent_uuid={integrated_agent.uuid} source=official"
            )
            return integrated_agent
        except IntegratedAgent.DoesNotExist:
            logger.info(
                f"[ORDER_STATUS] official_agent_not_found: "
                f"vtex_account={project.vtex_account} "
                f"project_uuid={project.uuid}"
            )

            try:
                integrated_agent = IntegratedAgent.objects.get(
                    parent_agent_uuid__isnull=False,
                    project=project,
                    is_active=True,
                )
                logger.info(
                    f"[ORDER_STATUS] agent_resolved: "
                    f"vtex_account={project.vtex_account} "
                    f"agent_uuid={integrated_agent.uuid} "
                    f"source=parent_agent "
                    f"parent_uuid={integrated_agent.parent_agent_uuid}"
                )
                return integrated_agent
            except IntegratedAgent.DoesNotExist:
                logger.info(
                    f"[ORDER_STATUS] no_agent_found: "
                    f"vtex_account={project.vtex_account} "
                    f"project_uuid={project.uuid}"
                )
                return None
            except IntegratedAgent.MultipleObjectsReturned:
                logger.error(
                    f"[ORDER_STATUS] multiple_parent_agents: "
                    f"vtex_account={project.vtex_account} "
                    f"project_uuid={project.uuid}"
                )
                raise ValidationError(
                    {
                        "error": "Multiple agents with parent_agent_uuid found for this project"
                    },
                    code="multiple_parent_agents",
                )

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
            logger.info(
                f"[ORDER_STATUS] project_not_found: vtex_account={vtex_account}"
            )
            return None
        except Project.MultipleObjectsReturned:
            logger.error(
                f"[ORDER_STATUS] multiple_projects: vtex_account={vtex_account}",
                exc_info=True,
            )
            return None

    def _is_duplicate_event(
        self,
        integrated_agent: IntegratedAgent,
        order_status_dto: OrderStatusDTO,
    ) -> bool:
        """
        Check whether an identical order status event was already processed
        within ORDER_STATUS_DUPLICATE_WINDOW_SECONDS.

        An "identical event" is uniquely defined by:
        project + integrated agent + order id + current state.

        Returns:
            True: an identical event is already registered in cache, so this
                call should be treated as a duplicate and skipped.
            False: the event is new within the window and has just been
                registered; processing should continue.
        """
        cache_key = (
            f"order_status_event:"
            f"{integrated_agent.project_id}:"
            f"{integrated_agent.uuid}:"
            f"{order_status_dto.orderId}:"
            f"{order_status_dto.currentState}"
        )
        event_registered_now = cache.add(
            cache_key,
            1,
            timeout=settings.ORDER_STATUS_DUPLICATE_WINDOW_SECONDS,
        )
        return not event_registered_now

    def execute(
        self,
        integrated_agent: IntegratedAgent,
        order_status_dto: OrderStatusDTO,
    ) -> None:
        vtex_account = order_status_dto.vtexAccount
        current_state = order_status_dto.currentState
        order_id = order_status_dto.orderId
        agent_uuid = integrated_agent.uuid

        if self._is_duplicate_event(integrated_agent, order_status_dto):
            logger.info(
                f"[ORDER_STATUS] duplicate_skipped: "
                f"vtex_account={vtex_account} agent_uuid={agent_uuid} "
                f"current_state={current_state} order_id={order_id}"
            )
            # Close the execution row opened by the upstream task; without
            # this skip the row would linger at `processing` until the
            # ZSET deadline force-finalises it as `Execution timed out`.
            self.exec_logger.log_execution_skip(
                reason="duplicate_order_status_event_within_window",
                skip_data={
                    "order_id": order_status_dto.orderId,
                    "current_state": order_status_dto.currentState,
                    "vtex_account": order_status_dto.vtexAccount,
                },
            )
            return

        logger.info(
            f"[ORDER_STATUS] executing: "
            f"vtex_account={vtex_account} agent_uuid={agent_uuid} "
            f"current_state={current_state} order_id={order_id}"
        )

        webhook_payload: Dict[str, Any] = adapt_order_status_to_webhook_payload(
            order_status_dto
        )

        request_data = RequestData(
            params={},
            payload=webhook_payload,
        )

        agent_webhook_use_case = AgentWebhookUseCase(exec_logger=self.exec_logger)
        credentials = agent_webhook_use_case._addapt_credentials(integrated_agent)

        request_data.set_credentials(credentials)
        request_data.set_ignored_official_rules(integrated_agent.ignore_templates)

        agent_webhook_use_case.execute(integrated_agent, request_data)
        logger.info(
            f"[ORDER_STATUS] executed: "
            f"vtex_account={vtex_account} agent_uuid={agent_uuid} "
            f"current_state={current_state} order_id={order_id}"
        )
