import json

import logging

import random

from typing import TYPE_CHECKING, Any, Dict, Optional, TypedDict

from uuid import UUID

from rest_framework.exceptions import NotFound

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


class AgentWebhookData(TypedDict):
    webhook_uuid: UUID


class AgentWebhookUseCase:
    def __init__(
        self,
        lambda_service: Optional[AwsLambdaServiceInterface] = None,
        flows_service: Optional[FlowsService] = None,
    ):
        self.lambda_service = lambda_service or AwsLambdaService()
        self.flows_service = flows_service or FlowsService(FlowsClient())

    def _get_integrated_agent(self, webhook_uuid: UUID):
        try:
            return IntegratedAgent.objects.get(uuid=webhook_uuid, is_active=True)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Assigned agent no found: {webhook_uuid}")

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

    def execute(
        self, payload: AgentWebhookData, data: "RequestData"
    ) -> Optional[Dict[str, Any]]:
        integrated_agent = self._get_integrated_agent(
            webhook_uuid=payload.get("webhook_uuid")
        )

        if not self._should_send_broadcast(integrated_agent):
            return None

        credentials = self._addapt_credentials(integrated_agent)

        data.set_credentials(credentials)
        data.set_ignored_official_rules(integrated_agent.ignore_templates)

        response = self._invoke_lambda(integrated_agent=integrated_agent, data=data)

        payload_raw = response.get("Payload").read().decode()
        data = json.loads(payload_raw)
        response["payload"] = data

        try:
            # verify if the lambda returned an error
            if isinstance(data, dict) and "errorMessage" in data:
                logger.error(f"Lambda execution error: {data.get('errorMessage')}")
                return

            template_name = self._get_current_template_name(integrated_agent, data)
            if not template_name:
                logger.error(f"Template not found: {template_name}")
                return response

            message = build_broadcast_template_message(
                data=data,
                channel_uuid=str(integrated_agent.channel_uuid),
                project_uuid=str(integrated_agent.project.uuid),
                template_name=template_name,
            )

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
