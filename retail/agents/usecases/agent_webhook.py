import hashlib

import secrets

from typing import Optional, Dict, Any, TypedDict

from uuid import UUID

from rest_framework.exceptions import NotFound, PermissionDenied

from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.agents.models import IntegratedAgent


class AgentWebhookData(TypedDict):
    client_secret: str
    webhook_uuid: UUID


class AgentWebhookUseCase:
    def __init__(self, lambda_service: Optional[AwsLambdaServiceInterface]):
        self.lambda_service = lambda_service or AwsLambdaService()

    def _get_integrated_agent(self, webhook_uuid: UUID):
        try:
            return IntegratedAgent.objects.get(uuid=webhook_uuid)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Assigned agent no found: {webhook_uuid}")

    def _is_client_secret_valid(self, stored_hash: str, client_secret: str) -> bool:
        salt_hex, hashed_secret = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        new_hash = hashlib.sha256(salt + client_secret.encode()).hexdigest()
        return secrets.compare_digest(new_hash, hashed_secret)

    def _invoke_lambda(self, function_name: str) -> Dict[str, Any]:
        return self.lambda_service.invoke(function_name)

    def execute(self, payload: AgentWebhookData) -> Dict[str, Any]:
        integrated_agent = self._get_integrated_agent(
            webhook_uuid=payload.get("webhook_uuid")
        )

        if not self._is_client_secret_valid(
            integrated_agent.client_secret, payload.get("client_secret")
        ):
            raise PermissionDenied("Invalid client secret.")

        return self._invoke_lambda(function_name=integrated_agent.lambda_arn)
