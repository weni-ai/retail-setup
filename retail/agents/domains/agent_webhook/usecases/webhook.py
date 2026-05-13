import logging

import random

from typing import Any, Dict, Mapping, Optional

from uuid import UUID

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.services.broadcast import (
    Broadcast,
)
from retail.agents.domains.agent_webhook.services.active_agent import (
    ActiveAgent,
)
from retail.agents.domains.agent_execution.services.logger import ExecutionLoggerService

from retail.agents.shared.cache import (
    IntegratedAgentCacheHandler,
    IntegratedAgentCacheHandlerRedis,
)
from retail.broadcasts.usecases.record_broadcast_sent import (
    BroadcastDispatchContext,
)
from retail.interfaces.clients.aws_lambda.client import RequestData

logger = logging.getLogger(__name__)


class AgentWebhookUseCase:
    def __init__(
        self,
        active_agent: Optional[ActiveAgent] = None,
        broadcast: Optional[Broadcast] = None,
        cache: Optional[IntegratedAgentCacheHandler] = None,
        exec_logger: Optional[ExecutionLoggerService] = None,
    ):
        self.active_agent = active_agent or ActiveAgent()
        self.broadcast_handler = broadcast or Broadcast()
        self.cache_handler = cache or IntegratedAgentCacheHandlerRedis()
        self.exec_logger = exec_logger or ExecutionLoggerService()
        self.IGNORE_INTEGRATED_AGENT_UUID = "d30bcce8-ce67-4677-8a33-c12b62a51d4f"

    def _get_integrated_agent(self, uuid: UUID):
        """Get integrated agent by UUID if active and not blocked."""
        if str(uuid) == self.IGNORE_INTEGRATED_AGENT_UUID:
            logger.info(f"Integrated agent is blocked: {uuid}")
            return None

        cached_integrated_agent = self.cache_handler.get_cached_agent(uuid)

        if cached_integrated_agent is not None:
            if self._is_project_blocked(cached_integrated_agent):
                logger.info(f"Project is blocked, skipping cached agent: {uuid}")
                return None
            return cached_integrated_agent

        try:
            db_integrated_agent = IntegratedAgent.objects.get(uuid=uuid, is_active=True)
        except IntegratedAgent.DoesNotExist:
            logger.info(f"Integrated agent not found: {uuid}")
            return None

        if self._is_project_blocked(db_integrated_agent):
            logger.info(f"Project is blocked, skipping agent: {uuid}")
            return None

        self.cache_handler.set_cached_agent(db_integrated_agent)
        return db_integrated_agent

    @staticmethod
    def _is_project_blocked(integrated_agent: IntegratedAgent) -> bool:
        """Return True when the agent's project is flagged as blocked."""
        return integrated_agent.project.is_blocked

    def _addapt_credentials(self, integrated_agent: IntegratedAgent) -> Dict[str, str]:
        """Convert integrated agent credentials to dictionary format."""
        credentials = integrated_agent.credentials.all()

        credentials_dict = {}
        for credential in credentials:
            credentials_dict[credential.key] = credential.value

        return credentials_dict

    def _should_send_broadcast(self, integrated_agent: IntegratedAgent) -> bool:
        """Determine if broadcast should be sent based on contact percentage."""
        percentage = integrated_agent.contact_percentage

        if percentage is None or percentage <= 0:
            return False

        if percentage >= 100:
            return True

        random_number = random.randint(1, 100)
        return random_number <= percentage

    def _set_project_rules(
        self, integrated_agent: IntegratedAgent, data: "RequestData"
    ) -> None:
        templates = integrated_agent.templates.filter(
            is_active=True, parent__isnull=True
        ).values("rule_code", "name")
        project_rules = [
            {"source": template["rule_code"], "template": template["name"]}
            for template in templates
            if template["rule_code"]
        ]
        data.set_project_rules(project_rules)

    def _process_lambda_response(
        self,
        integrated_agent: IntegratedAgent,
        parsed_data: Dict[str, Any],
        dispatch_context: Optional[BroadcastDispatchContext] = None,
    ) -> Optional[Dict[str, Any]]:
        """Process parsed lambda response and build broadcast message.

        Args:
            integrated_agent: The integrated agent
            parsed_data: Already parsed lambda response data (parse only once
                         since AWS Lambda StreamingBody can only be read once)
            dispatch_context: Optional commercial origin (order_form_id /
                order_id) captured pre-Lambda so the persisted
                BroadcastMessage row can later be matched against an
                ``invoiced`` event for conversion attribution.
        """
        exec_logger = self.exec_logger
        data = parsed_data

        # Update contact_urn if we now have it from lambda response
        if data.get("contact_urn"):
            exec_logger.update_contact_urn(contact_urn=data["contact_urn"])

        if not self.active_agent.validate_response(data, integrated_agent):
            exec_logger.log_execution_skip(
                reason="Lambda response validation failed",
                skip_data={"status": data.get("status"), "error": data.get("error")},
            )
            return None

        if not self.broadcast_handler.can_send_to_contact(integrated_agent, data):
            logger.info("Contact is not allowed to receive the broadcast.")
            exec_logger.log_execution_skip(
                reason="Contact not allowed to receive broadcast",
                skip_data={"contact_urn": data.get("contact_urn")},
            )
            return None

        try:
            message = self.broadcast_handler.build_message(integrated_agent, data)
            if not message:
                logger.info(
                    f"Failed to build broadcast message from payload data: {data}"
                )
                exec_logger.log_execution_error(
                    error_message="Failed to build broadcast message",
                    error_data={"payload_data": data},
                )
                return None

            dispatch_result = self.broadcast_handler.send_message(
                message,
                integrated_agent,
                data,
                dispatch_context=dispatch_context,
            )
            broadcast_response = dispatch_result.response
            broadcast_message_uuid = dispatch_result.broadcast_message_uuid

            template = self.broadcast_handler.get_current_template(
                integrated_agent, data
            )
            template_uuid = (
                template.uuid if template and template is not False else None
            )
            broadcast_id = broadcast_response.get("id") if broadcast_response else None

            exec_logger.log_broadcast_sent(
                broadcast_response=broadcast_response or {},
                template_uuid=template_uuid,
                broadcast_id=broadcast_id,
                broadcast_message_uuid=broadcast_message_uuid,
            )

            return data

        except Exception as e:
            logger.exception(f"Unexpected error while building broadcast message: {e}")
            exec_logger.log_execution_error(
                error_message=f"Error building/sending broadcast: {str(e)}",
            )
            return None

    def execute(
        self, integrated_agent: IntegratedAgent, data: "RequestData"
    ) -> Optional[Dict[str, Any]]:
        """Execute agent webhook broadcast process.

        Returns the Lambda response dict when the broadcast was successfully
        dispatched to Flows, or None when it was not sent for any reason
        (sampling, restrictions, Lambda failures, etc.).
        """
        logger.info(f"Executing broadcast for agent: {integrated_agent.uuid}")
        exec_logger = self.exec_logger

        # Wrapping here guarantees the trace lands
        # regardless of who invokes the use case. The exception is
        # re-raised so outer handlers (e.g. `task_agent_webhook`'s
        # `except`) keep their current behaviour.
        try:
            if not self._should_send_broadcast(integrated_agent):
                logger.info("Broadcast not allowed for this agent.")
                exec_logger.log_execution_skip(
                    reason="Broadcast not allowed (contact percentage check)",
                    skip_data={
                        "contact_percentage": integrated_agent.contact_percentage
                    },
                )
                return None

            self._set_project_rules(integrated_agent, data)

            exec_logger.log_lambda_request(
                request_data={
                    "params": dict(data.params) if data.params else {},
                    "payload": dict(data.payload) if data.payload else {},
                    "project_rules": data.project_rules,
                },
            )

            # Captured pre-Lambda so attribution survives Lambdas that drop
            # the order identifiers from their response.
            dispatch_context = self._extract_dispatch_context(data.payload)

            response = self.active_agent.invoke(
                integrated_agent=integrated_agent, data=data
            )

            parsed_response = self.active_agent.parse_response(response)
            log_tail = self.active_agent.parse_log_tail(response)

            exec_logger.log_lambda_response(
                response_data=parsed_response or {"error": "Failed to parse response"},
                log_tail=log_tail,
            )

            if not parsed_response:
                logger.info("Error in parsing lambda response.")
                exec_logger.log_execution_error(
                    error_message="Error parsing lambda response",
                )
                return None

            result = self._process_lambda_response(
                integrated_agent,
                parsed_response,
                dispatch_context=dispatch_context,
            )

            if result:
                logger.info(
                    f"Successfully executed broadcast for agent: {integrated_agent.uuid}"
                )

            return result
        except Exception as e:
            exec_logger.log_execution_error(
                error_message=str(e),
                error_data={"phase": "agent_webhook_execute"},
            )
            raise

    @staticmethod
    def _extract_dispatch_context(
        payload: Optional[Mapping[Any, Any]],
    ) -> Optional[BroadcastDispatchContext]:
        """Build a ``BroadcastDispatchContext`` from the request payload.

        Reads the two literal keys our orchestrators populate today
        (``order_form_id`` from cart abandonment, ``OrderId`` from the
        VTEX-shaped order-status / payment-recovery webhook). Any
        other dispatch path leaves the context as ``None`` because
        there is no commercial origin to track.
        """
        if not payload:
            return None
        order_form_id = payload.get("order_form_id")
        order_id = payload.get("OrderId")
        if not order_form_id and not order_id:
            return None
        return BroadcastDispatchContext(
            order_form_id=str(order_form_id) if order_form_id else None,
            order_id=str(order_id) if order_id else None,
        )
