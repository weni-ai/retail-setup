import json

import logging

import random

from typing import TYPE_CHECKING, Any, Dict, Optional

from uuid import UUID

from retail.agents.models import IntegratedAgent
from retail.agents.utils import build_broadcast_template_message
from retail.clients.flows.client import FlowsClient
from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.services.flows.service import FlowsService
from retail.templates.models import Template

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from retail.interfaces.clients.aws_lambda.client import RequestData


class AgentWebhookUseCase:
    def __init__(
        self,
        lambda_service: Optional[AwsLambdaServiceInterface] = None,
        flows_service: Optional[FlowsService] = None,
    ):
        self.lambda_service = lambda_service or AwsLambdaService()
        self.flows_service = flows_service or FlowsService(FlowsClient())
        self.MISSING_TEMPLATE_ERROR = "Missing template"

    def _get_integrated_agent(self, uuid: UUID):
        if str(uuid) == "d30bcce8-ce67-4677-8a33-c12b62a51d4f":
            logger.info(f"Integrated agent is blocked: {uuid}")
            return None

        try:
            return IntegratedAgent.objects.get(uuid=uuid, is_active=True)
        except IntegratedAgent.DoesNotExist:
            logger.info(f"Integrated agent not found: {uuid}")
            return None

    def _invoke_lambda(
        self, integrated_agent: IntegratedAgent, data: "RequestData"
    ) -> Dict[str, Any]:
        function_name = integrated_agent.agent.lambda_arn
        project = integrated_agent.project

        return self.lambda_service.invoke(
            function_name,
            {
                "params": data.params,
                "payload": data.payload,
                "credentials": data.credentials,
                "ignore_official_rules": integrated_agent.ignore_templates,
                "project": {
                    "uuid": str(project.uuid),
                    "vtex_account": project.vtex_account,
                },
            },
        )

    def _addapt_credentials(self, integrated_agent: IntegratedAgent) -> Dict[str, str]:
        credentials = integrated_agent.credentials.all()

        credentials_dict = {}
        for credential in credentials:
            credentials_dict[credential.key] = credential.value

        return credentials_dict

    def _should_send_broadcast(self, integrated_agent: IntegratedAgent) -> bool:
        percentage = integrated_agent.contact_percentage

        if percentage is None or percentage <= 0:
            return False

        if percentage >= 100:
            return True

        random_number = random.randint(1, 100)
        return random_number <= percentage

    def _can_send_to_contact(
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

        # Step 1: Load config and fallback gracefully
        config = integrated_agent.config or {}
        if not config:
            return True  # No config → no restriction → allow

        # Step 2: Access nested restriction data
        integration_settings = config.get("integration_settings", {})
        order_status_restriction = integration_settings.get("order_status_restriction")

        # Step 3: If restriction block is not defined or not active, allow
        if not order_status_restriction or not order_status_restriction.get(
            "is_active", False
        ):
            return True

        # Step 4: Validate contact against allowed list
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

    def execute(
        self, integrated_agent: IntegratedAgent, data: "RequestData"
    ) -> Optional[Dict[str, Any]]:
        logger.info(f"Executing broadcast for agent: {integrated_agent.uuid}")

        if not self._should_send_broadcast(integrated_agent):
            logger.info("Broadcast not allowed for this agent.")
            return None

        response = self._invoke_lambda(integrated_agent=integrated_agent, data=data)

        data = json.loads(response.get("Payload").read().decode())

        if data.get("error") and data.get("error") == self.MISSING_TEMPLATE_ERROR:
            logger.info("Missing template error encountered.")
            return None

        response["payload"] = data

        if not self._can_send_to_contact(integrated_agent, data):
            logger.info("Contact is not allowed to receive the broadcast.")
            return None

        try:
            # verify if the lambda returned an error
            if isinstance(data, dict) and "errorMessage" in data:
                logger.error(f"Lambda execution error: {data.get('errorMessage')}")
                return

            logger.info("Retrieving current template name.")
            template_name = self._get_current_template_name(integrated_agent, data)
            if not template_name:
                logger.error(f"Template not found: {template_name}")
                return response

            logger.info("Building broadcast template message.")
            message = build_broadcast_template_message(
                data=data,
                channel_uuid=str(integrated_agent.channel_uuid),
                project_uuid=str(integrated_agent.project.uuid),
                template_name=template_name,
            )
            logger.info(f"Broadcast template message built: {message}")

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON payload: {e}")
            return response

        except Exception as e:
            logger.exception(f"Unexpected error while building broadcast message: {e}")
            return response

        if not message:
            logger.error(f"Failed to build broadcast message from payload data: {data}")
            return response

        self._send_broadcast_message(message)
        logger.info(
            f"Successfully executed broadcast for agent: {integrated_agent.uuid}"
        )
        return response

    def _send_broadcast_message(self, message: Dict[str, Any]):
        response = self.flows_service.send_whatsapp_broadcast(message)
        logger.info(f"Broadcast message sent: {response}")

    def _get_current_template_name(
        self, integrated_agent: IntegratedAgent, data: Dict[str, Any]
    ) -> str:
        template_name = data.get("template")
        try:
            template = integrated_agent.templates.get(name=template_name)
            return template.current_version.template_name
        except Template.DoesNotExist:
            return None
