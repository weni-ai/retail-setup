import json

import logging

import random

from enum import IntEnum

from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from uuid import UUID

from datetime import datetime

from retail.agents.models import IntegratedAgent
from retail.agents.utils import build_broadcast_template_message
from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.services.flows.service import FlowsService
from retail.templates.models import Template
from retail.agents.handlers.cache.integrated_agent_webhook import (
    IntegratedAgentCacheHandler,
    IntegratedAgentCacheHandlerRedis,
)
from weni_datalake_sdk.clients.client import send_commerce_webhook_data
from weni_datalake_sdk.paths.commerce_webhook import CommerceWebhookPath


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
    GLOBAL_RULE_FAILED = 5
    GLOBAL_RULE_NOT_MATCHED = 6


class LambdaHandler:
    def __init__(
        self,
        lambda_service: Optional[AwsLambdaServiceInterface] = None,
    ):
        self.lambda_service = lambda_service or AwsLambdaService()

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
                "project_rules": data.project_rules,
                "global_rule": integrated_agent.global_rule_code,
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

    def validate_response(
        self, data: Dict[str, Any], integrated_agent: IntegratedAgent
    ) -> bool:
        """Validate lambda response for errors based on status codes."""
        status_code = data.get("status")
        error = data.get("error")

        if status_code is not None:
            match status_code:
                case LambdaResponseStatus.RULE_MATCHED:
                    return True
                case LambdaResponseStatus.RULE_NOT_MATCHED:
                    logger.info(
                        f"Rule not matched for integrated agent {integrated_agent.uuid}: {error}"
                    )
                    return False
                case LambdaResponseStatus.PRE_PROCESSING_FAILED:
                    logger.info(
                        f"Pre-processing failed for integrated agent {integrated_agent.uuid}: {error}"
                    )
                    return False
                case LambdaResponseStatus.CUSTOM_RULE_FAILED:
                    logger.info(
                        f"Custom rule failed for integrated agent {integrated_agent.uuid}: {error}"
                    )
                    return False
                case LambdaResponseStatus.OFFICIAL_RULE_FAILED:
                    logger.info(
                        f"Official rule failed for integrated agent {integrated_agent.uuid}: {error}"
                    )
                    return False
                case LambdaResponseStatus.GLOBAL_RULE_FAILED:
                    logger.info(
                        f"Global rule failed for integrated agent {integrated_agent.uuid}: {error}"
                    )
                    return False
                case LambdaResponseStatus.GLOBAL_RULE_NOT_MATCHED:
                    logger.info(
                        f"Global rule not matched for integrated agent {integrated_agent.uuid}: {error}"
                    )
                    return False
                case _:
                    logger.warning(
                        f"Unknown status code for integrated agent {integrated_agent.uuid}: {status_code}"
                    )
                    return False

        if isinstance(data, dict) and "errorMessage" in data:
            logger.error(f"Lambda execution error: {data.get('errorMessage')}")
            return False

        return False


class BroadcastHandler:
    def __init__(
        self, flows_service: Optional[FlowsService] = None, audit_func: Callable = None
    ):
        self.flows_service = flows_service or FlowsService()
        self.audit_func = audit_func or send_commerce_webhook_data

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

    def send_message(
        self,
        message: Dict[str, Any],
        integrated_agent: IntegratedAgent,
        lambda_data: Optional[Dict[str, Any]] = None,
    ):
        """Send broadcast message via flows service."""
        response = self.flows_service.send_whatsapp_broadcast(message)
        self._register_broadcast_event(message, response, integrated_agent, lambda_data)
        logger.info(f"Broadcast message sent: {response}")

    def get_current_template_name(
        self, integrated_agent: IntegratedAgent, data: Dict[str, Any]
    ) -> Optional[str | bool]:
        """Get current template name from integrated agent templates."""
        template_name = data.get("template")
        try:
            template = integrated_agent.templates.get(name=template_name)
            if template.current_version is None:
                logger.info(f"Template {template_name} has no current version.")
                return False
            return template.current_version.template_name
        except Template.DoesNotExist:
            return None

    def build_message(
        self, integrated_agent: IntegratedAgent, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build broadcast message from lambda response data."""
        logger.info("Retrieving current template name.")
        template_name = self.get_current_template_name(integrated_agent, data)

        if template_name is False:
            logger.info(
                "Could not build message because template has no current version."
            )
            return

        if template_name is None:
            logger.error(f"Template not found: {template_name}")
            return

        logger.info("Building broadcast template message.")
        message = build_broadcast_template_message(
            data=data,
            channel_uuid=str(integrated_agent.channel_uuid),
            project_uuid=str(integrated_agent.project.uuid),
            template_name=template_name,
        )
        logger.info(f"Broadcast template message built: {message}")
        return message

    def _register_broadcast_event(
        self,
        message: Dict[str, Any],
        response: Dict[str, Any],
        integrated_agent: IntegratedAgent,
        lambda_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Register broadcast event with structured data according to protobuf schema.

        The method extracts data from lambda_data (preferred) or message, following this priority:
        - status: from lambda_data["status"] (ResponseStatus enum values, default: 0)
        - template: from lambda_data["template"] or message structure
        - template_variables: from lambda_data["template_variables"] or message structure (always list)
        - contact_urn: from lambda_data["contact_urn"] or message structure
        - error: from response["error"] (always list)
        - data: {"event_type": "template_broadcast_sent"} (identifies this as template broadcast event)

        Args:
            message: The broadcast message sent to flows service
            response: The response from flows service
            integrated_agent: The integrated agent instance
            lambda_data: Lambda response data containing status, template, template_variables, contact_urn
        """

        # Extract template name from lambda data or message
        template_name = ""
        if lambda_data and "template" in lambda_data:
            template_name = lambda_data["template"]
        elif message and "msg" in message and "template" in message["msg"]:
            template_name = message["msg"]["template"].get("name")

        # Extract contact_urn from lambda data or message
        contact_urn = ""
        if lambda_data and "contact_urn" in lambda_data:
            contact_urn = lambda_data["contact_urn"]
        elif message and "urns" in message and message["urns"]:
            contact_urn = message["urns"][0]

        # Extract template variables from lambda data or message (always return list)
        template_variables = []
        if lambda_data and "template_variables" in lambda_data:
            template_variables = lambda_data["template_variables"]
        elif message and "msg" in message and "template" in message["msg"]:
            template_variables = message["msg"]["template"].get("variables", [])

        # Extract error information if present (always return list)
        error_data = []
        if response and "error" in response:
            error_data = [response["error"]]

        # Build structured data to protobuf schema
        event_data = {
            "template": template_name,
            "template_variables": template_variables,
            "contact_urn": contact_urn,
            "error": error_data,
            "data": {"event_type": "template_broadcast_sent"},
            "date": datetime.now().isoformat(),
            "project": str(integrated_agent.project.uuid),
            "request": message,
            "response": response,
            "agent": str(integrated_agent.agent.uuid),
        }

        # Only include status if it exists in lambda_data
        if lambda_data and "status" in lambda_data:
            event_data["status"] = lambda_data["status"]

        print(f"Sending event data: {event_data}")
        print(f"CommerceWebhookPath: {CommerceWebhookPath}")
        self.audit_func(CommerceWebhookPath, event_data)


class AgentWebhookUseCase:
    def __init__(
        self,
        lambda_handler: Optional[LambdaHandler] = None,
        broadcast_handler: Optional[BroadcastHandler] = None,
        cache_handler: Optional[IntegratedAgentCacheHandler] = None,
    ):
        self.lambda_handler = lambda_handler or LambdaHandler()
        self.broadcast_handler = broadcast_handler or BroadcastHandler()
        self.cache_handler = cache_handler or IntegratedAgentCacheHandlerRedis()
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

    def _process_lambda_response(
        self, integrated_agent: IntegratedAgent, response: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Process lambda response and build broadcast message."""
        data = self.lambda_handler.parse_response(response)

        if not data:
            logger.info("Error in parsing lambda response.")
            return None

        response["payload"] = data

        if not self.lambda_handler.validate_response(data, integrated_agent):
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

        response = self.lambda_handler.invoke(
            integrated_agent=integrated_agent, data=data
        )
        result = self._process_lambda_response(integrated_agent, response)

        if result:
            logger.info(
                f"Successfully executed broadcast for agent: {integrated_agent.uuid}"
            )
