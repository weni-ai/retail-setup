from typing import TYPE_CHECKING, Any, Dict, Optional, TypedDict
from uuid import UUID

from rest_framework.exceptions import NotFound

from retail.agents.models import IntegratedAgent
from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService

if TYPE_CHECKING:
    from retail.interfaces.clients.aws_lambda.client import RequestData


class AgentWebhookData(TypedDict):
    webhook_uuid: UUID


class AgentWebhookUseCase:
    def __init__(self, lambda_service: Optional[AwsLambdaServiceInterface] = None):
        self.lambda_service = lambda_service or AwsLambdaService()

    def _get_integrated_agent(self, webhook_uuid: UUID):
        try:
            return IntegratedAgent.objects.get(uuid=webhook_uuid)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Assigned agent no found: {webhook_uuid}")

    def _invoke_lambda(self, function_name: str, data: "RequestData") -> Dict[str, Any]:
        return self.lambda_service.invoke(function_name, data)

    def execute(self, payload: AgentWebhookData, data: "RequestData") -> Dict[str, Any]:
        integrated_agent = self._get_integrated_agent(
            webhook_uuid=payload.get("webhook_uuid")
        )

        return self._invoke_lambda(
            function_name=integrated_agent.agent.lambda_arn, data=data
        )
