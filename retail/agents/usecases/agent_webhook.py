import json

import logging

import random

from enum import IntEnum

from typing import TYPE_CHECKING, Any, Dict, Optional, List

from uuid import UUID

from retail.agents.models import IntegratedAgent
from retail.agents.utils import build_broadcast_template_message
from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.services.flows.service import FlowsService
from retail.templates.models import Template

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from retail.interfaces.clients.aws_lambda.client import RequestData


class LambdaResponseStatus(IntEnum):
    """Enum for possible Lambda response statuses."""

    RULE_MATCHED = 0
    RULE_NOT_MATCHED = 1
    PRE_PROCESSING_FAILED = 2
    CUSTOM_RULE_FAILED = 3
    OFFICIAL_RULE_FAILED = 4


class LambdaHandler:
    def __init__(self, lambda_service: Optional[AwsLambdaServiceInterface] = None):
        self.lambda_service = lambda_service or AwsLambdaService()
        self.MISSING_TEMPLATE_ERROR = "Missing template"

    def _get_project_rules_payload(
        self, integrated_agent: IntegratedAgent
    ) -> List[Dict[str, str]]:
        rule_codes = integrated_agent.templates.filter(
            is_active=True, parent__isnull=True
        ).values_list("rule_code", flat=True)

        return [{"source": rule_code} for rule_code in rule_codes if rule_code]

    def invoke(
        self, integrated_agent: IntegratedAgent, data: "RequestData"
    ) -> Dict[str, Any]:
        """Invoke lambda function with agent and request data."""
        function_name = integrated_agent.agent.lambda_arn
        project = integrated_agent.project

        return self.lambda_service.invoke(
            function_name,
            {
                "params": data.params,
                "payload": data.payload,
                "credentials": data.credentials,
                "ignore_official_rules": integrated_agent.ignore_templates,
                "project_rules": self._get_project_rules_payload(integrated_agent),
                "project": {
                    "uuid": str(project.uuid),
                    "vtex_account": project.vtex_account,
                },
            },
        )

    def parse_response(self, response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse lambda response and extract payload data."""
        try:
            data = json.loads(response.get("Payload").read().decode())
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON payload: {e}")
            return None

    def validate_response(self, data: Dict[str, Any]) -> bool:
        """Validate lambda response for errors based on status codes."""
        status_code = data.get("status")
        error = data.get("error")

        if status_code is not None:
            match status_code:
                case LambdaResponseStatus.RULE_MATCHED:
                    return True
                case LambdaResponseStatus.RULE_NOT_MATCHED:
                    logger.info(f"Rule not matched: {error}")
                    return False
                case LambdaResponseStatus.PRE_PROCESSING_FAILED:
                    logger.info(f"Pre-processing failed: {error}")
                    return False
                case LambdaResponseStatus.CUSTOM_RULE_FAILED:
                    logger.info(f"Custom rule failed: {error}")
                    return False
                case LambdaResponseStatus.OFFICIAL_RULE_FAILED:
                    logger.info(f"Official rule failed: {error}")
                    return False
                case _:
                    logger.warning(f"Unknown status code: {status_code}")
                    return False

        if isinstance(data, dict) and "errorMessage" in data:
            logger.error(f"Lambda execution error: {data.get('errorMessage')}")
            return False

        return False


class BroadcastHandler:
    def __init__(self, flows_service: Optional[FlowsService] = None):
        self.flows_service = flows_service or FlowsService()

    def can_send_to_contact(
        self, integrated_agent: IntegratedAgent, data: Dict[str, Any]
    ) -> bool:
        """
        Validates whether a contact is allowed to receive the broadcast based on phone restrictions.

        If the 'order_status_restriction' config is present and active, only contacts explicitly listed
        in 'allowed_phone_numbers' will be allowed. If no restriction config exists or is inactive,
        the broadcast is allowed.

        Args:
            integrated_agent (IntegratedAgent): The agent that may have restrictions configured.
            data (Dict[str, Any]): The payload received from the lambda, expected to contain 'contact_urn'.

        Returns:
            bool: True if the message is allowed to be sent, False if it should be blocked.

        Example of valid config:
        {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": true,
                    "allowed_phone_numbers": [
                        "whatsapp:5584996765245",
                        "whatsapp:558498887766"
                    ]
                }
            }
        }
        """
        contact_urn = data.get("contact_urn")
        if not contact_urn:
            logger.warning(
                f"No 'contact_urn' found in payload {data}. Skipping restriction check."
            )
            return False

        config = integrated_agent.config or {}
        if not config:
            return True

        integration_settings = config.get("integration_settings", {})
        order_status_restriction = integration_settings.get("order_status_restriction")

        if not order_status_restriction or not order_status_restriction.get(
            "is_active", False
        ):
            return True

        allowed_numbers = order_status_restriction.get("allowed_phone_numbers")
        if not allowed_numbers:
            logger.info(
                f"Restriction active, but 'allowed_phone_numbers' is missing or empty "
                f"for agent {integrated_agent.uuid}. Blocking by default."
            )
            return False

        if contact_urn not in allowed_numbers:
            logger.info(
                f"Blocked contact due to restriction: {contact_urn} not in "
                f"allowed_phone_numbers for agent {integrated_agent.uuid}."
            )
            return False

        return True

    def send_message(self, message: Dict[str, Any]):
        """Send broadcast message via flows service."""
        response = self.flows_service.send_whatsapp_broadcast(message)
        logger.info(f"Broadcast message sent: {response}")

    def get_current_template_name(
        self, integrated_agent: IntegratedAgent, data: Dict[str, Any]
    ) -> str:
        """Get current template name from integrated agent templates."""
        template_name = data.get("template")
        try:
            template = integrated_agent.templates.get(name=template_name)
            return template.current_version.template_name
        except Template.DoesNotExist:
            return None

    def build_message(
        self, integrated_agent: IntegratedAgent, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build broadcast message from lambda response data."""
        logger.info("Retrieving current template name.")
        template_name = self.get_current_template_name(integrated_agent, data)
        if not template_name:
            logger.error(f"Template not found: {template_name}")
            return None

        logger.info("Building broadcast template message.")
        message = build_broadcast_template_message(
            data=data,
            channel_uuid=str(integrated_agent.channel_uuid),
            project_uuid=str(integrated_agent.project.uuid),
            template_name=template_name,
        )
        logger.info(f"Broadcast template message built: {message}")
        return message


class AgentWebhookUseCase:
    def __init__(
        self,
        lambda_handler: Optional[LambdaHandler] = None,
        broadcast_handler: Optional[BroadcastHandler] = None,
    ):
        self.lambda_handler = lambda_handler or LambdaHandler()
        self.broadcast_handler = broadcast_handler or BroadcastHandler()
        self.IGNORE_INTEGRATED_AGENT_UUID = "d30bcce8-ce67-4677-8a33-c12b62a51d4f"

    def _get_integrated_agent(self, uuid: UUID):
        """Get integrated agent by UUID if active and not blocked."""
        if str(uuid) == self.IGNORE_INTEGRATED_AGENT_UUID:
            logger.info(f"Integrated agent is blocked: {uuid}")
            return None

        try:
            return IntegratedAgent.objects.get(uuid=uuid, is_active=True)
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

    def _process_lambda_response(
        self, integrated_agent: IntegratedAgent, response: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Process lambda response and build broadcast message."""
        data = self.lambda_handler.parse_response(response)
        if not data:
            return response

        response["payload"] = data

        if not self.lambda_handler.validate_response(data):
            return None

        if not self.broadcast_handler.can_send_to_contact(integrated_agent, data):
            logger.info("Contact is not allowed to receive the broadcast.")
            return None

        try:
            message = self.broadcast_handler.build_message(integrated_agent, data)
            if not message:
                logger.error(
                    f"Failed to build broadcast message from payload data: {data}"
                )
                return response

            self.broadcast_handler.send_message(message)
            return response

        except Exception as e:
            logger.exception(f"Unexpected error while building broadcast message: {e}")
            return response

    def execute(
        self, integrated_agent: IntegratedAgent, data: "RequestData"
    ) -> Optional[Dict[str, Any]]:
        """Execute agent webhook broadcast process."""
        logger.info(f"Executing broadcast for agent: {integrated_agent.uuid}")

        if not self._should_send_broadcast(integrated_agent):
            logger.info("Broadcast not allowed for this agent.")
            return None

        response = self.lambda_handler.invoke(
            integrated_agent=integrated_agent, data=data
        )
        result = self._process_lambda_response(integrated_agent, response)

        if result:
            logger.info(
                f"Successfully executed broadcast for agent: {integrated_agent.uuid}"
            )

        return result
