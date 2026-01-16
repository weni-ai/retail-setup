import json
import logging
import random

from typing import Any, Dict, Optional

from uuid import UUID

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.services.broadcast import (
    Broadcast,
)
from retail.agents.domains.agent_webhook.services.active_agent import (
    ActiveAgent,
)

from retail.agents.shared.cache import (
    IntegratedAgentCacheHandler,
    IntegratedAgentCacheHandlerRedis,
)
from retail.interfaces.clients.aws_lambda.client import RequestData

logger = logging.getLogger(__name__)


class AgentWebhookUseCase:
    def __init__(
        self,
        active_agent: Optional[ActiveAgent] = None,
        broadcast: Optional[Broadcast] = None,
        cache: Optional[IntegratedAgentCacheHandler] = None,
    ):
        self.active_agent = active_agent or ActiveAgent()
        self.broadcast_handler = broadcast or Broadcast()
        self.cache_handler = cache or IntegratedAgentCacheHandlerRedis()
        self.IGNORE_INTEGRATED_AGENT_UUID = "d30bcce8-ce67-4677-8a33-c12b62a51d4f"

    def _get_integrated_agent(self, uuid: UUID):
        """Get integrated agent by UUID if active and not blocked."""
        if str(uuid) == self.IGNORE_INTEGRATED_AGENT_UUID:
            logger.info(f"Integrated agent is blocked: {uuid}")
            return None

        cached_integrated_agent = self.cache_handler.get_cached_agent(uuid)

        if cached_integrated_agent is not None:
            return cached_integrated_agent

        try:
            db_integrated_agent = IntegratedAgent.objects.get(uuid=uuid, is_active=True)
            self.cache_handler.set_cached_agent(db_integrated_agent)
            return db_integrated_agent
        except IntegratedAgent.DoesNotExist:
            logger.info(f"Integrated agent not found: {uuid}")
            return None

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

    def _log_execution_trace(self, data: Dict[str, Any]) -> None:
        """Log execution trace from Lambda response."""
        execution_trace = data.pop("_execution_trace", None)

        if execution_trace:
            logger.info(f"[ExecutionTrace] {json.dumps(execution_trace, default=str)}")

    def _process_lambda_response(
        self, integrated_agent: IntegratedAgent, response: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Process lambda response and build broadcast message."""
        data = self.active_agent.parse_response(response)

        if not data:
            logger.info("Error in parsing lambda response.")
            return None

        self._log_execution_trace(data)

        response["payload"] = data

        if not self.active_agent.validate_response(data, integrated_agent):
            return None

        if not self.broadcast_handler.can_send_to_contact(integrated_agent, data):
            logger.info("Contact is not allowed to receive the broadcast.")
            return None

        try:
            message = self.broadcast_handler.build_message(integrated_agent, data)
            if not message:
                logger.info(
                    f"Failed to build broadcast message from payload data: {data}"
                )
                return None

            self.broadcast_handler.send_message(message, integrated_agent, data)
            return response

        except Exception as e:
            logger.exception(f"Unexpected error while building broadcast message: {e}")
            return None

    def execute(self, integrated_agent: IntegratedAgent, data: "RequestData") -> None:
        """Execute agent webhook broadcast process."""
        logger.info(f"Executing broadcast for agent: {integrated_agent.uuid}")

        if not self._should_send_broadcast(integrated_agent):
            logger.info("Broadcast not allowed for this agent.")
            return None

        self._set_project_rules(integrated_agent, data)

        response = self.active_agent.invoke(
            integrated_agent=integrated_agent, data=data
        )
        result = self._process_lambda_response(integrated_agent, response)

        if result:
            logger.info(
                f"Successfully executed broadcast for agent: {integrated_agent.uuid}"
            )
