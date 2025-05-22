import json

import logging

from typing import TYPE_CHECKING, Any, Dict, Optional, TypedDict
from uuid import UUID

from rest_framework.exceptions import NotFound

from retail.agents.models import IntegratedAgent
from retail.agents.utils import build_broadcast_template_message
from retail.clients.flows.client import FlowsClient
from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.services.flows.service import FlowsService


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
            return IntegratedAgent.objects.get(uuid=webhook_uuid)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Assigned agent no found: {webhook_uuid}")

    def _invoke_lambda(self, function_name: str, data: "RequestData") -> Dict[str, Any]:
        return self.lambda_service.invoke(function_name, data)

    def _addapt_credentials(self, integrated_agent: IntegratedAgent) -> Dict[str, str]:
        credentials = integrated_agent.credentials.all()

        crdentials_dict = {}
        for credential in credentials:
            crdentials_dict[credential.key] = credential.value

        return crdentials_dict

    def execute(
        self, payload: AgentWebhookData, data: "RequestData"
    ) -> Optional[Dict[str, Any]]:
        integrated_agent = self._get_integrated_agent(
            webhook_uuid=payload.get("webhook_uuid")
        )

        credentials = self._addapt_credentials(integrated_agent)

        data.set_credentials(credentials)

        response = self._invoke_lambda(
            function_name=integrated_agent.agent.lambda_arn, data=data
        )

        try:
            payload_raw = response.get("Payload", "{}")
            data = json.loads(payload_raw)

            # verify if the lambda returned an error
            if isinstance(data, dict) and "errorMessage" in data:
                logger.error(f"Lambda execution error: {data.get('errorMessage')}")
                return

            message = build_broadcast_template_message(
                data=data,
                channel_uuid=integrated_agent.channel_uuid,
                project_uuid=integrated_agent.project.uuid,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON payload: {e}")
            return

        except Exception as e:
            logger.exception(f"Unexpected error while building broadcast message: {e}")
            return

        if not message:
            logger.error(f"Failed to build broadcast message from payload data: {data}")
            return

        self._send_broadcast_message(message, integrated_agent.project.uuid)
        logger.info(
            f"Successfully executed broadcast for agent: {integrated_agent.uuid}"
        )

    def _send_broadcast_message(self, message: Dict[str, Any], project_uuid: str):
        response = self.flows_service.send_whatsapp_broadcast(
            message, project_uuid=project_uuid
        )
        logger.info(f"Broadcast message sent: {response}, for project: {project_uuid}")
