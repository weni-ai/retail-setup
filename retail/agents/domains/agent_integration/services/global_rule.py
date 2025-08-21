import json

from typing import Optional, Dict, Any

from enum import IntEnum

from rest_framework.exceptions import APIException

from django.conf import settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.exceptions import (
    GlobalRuleBadRequest,
    GlobalRuleInternalServerError,
    GlobalRuleUnprocessableEntity,
)
from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService


class LambdaResponseStatusCode(IntEnum):
    OK = 200
    BAD_REQUEST = 400
    UNPROCESSABLE_ENTITY = 422


class GlobalRule:
    def __init__(
        self, lambda_service: Optional[AwsLambdaServiceInterface] = None
    ) -> None:
        self.lambda_service = lambda_service or AwsLambdaService(
            region_name=getattr(settings, "LAMBDA_CODE_GENERATOR_REGION", "us-east-1"),
        )
        self.lambda_code_generator = getattr(
            settings,
            "LAMBDA_CODE_GENERATOR",
            "arn:aws:lambda:us-east-1:123456789012:function:mock",
        )
        self.response: Optional[Dict[str, Any]] = None
        self.global_rule_code: Optional[str] = None

    def generate(
        self, integrated_agent: IntegratedAgent, global_rule: str
    ) -> "GlobalRule":
        payload = {
            "parameters": [
                {
                    "name": "examples",
                    "value": integrated_agent.agent.examples,
                },
            ],
            "global_rule": global_rule,
        }

        response = self.lambda_service.invoke(
            function_name=self.lambda_code_generator, payload=payload
        )

        response_payload = json.loads(response["Payload"].read())

        self.response = response_payload

        return self

    def validate(self) -> "GlobalRule":
        if self.response is None:
            raise APIException(detail="Could not get a response from lambda.")

        status_code = self.response.get("statusCode")
        body = self.response.get("body")

        if status_code is not None:
            match status_code:
                case LambdaResponseStatusCode.OK:
                    self.global_rule_code = body.get("global_rule").get(
                        "generated_code"
                    )
                    return self
                case LambdaResponseStatusCode.BAD_REQUEST:
                    raise GlobalRuleBadRequest(detail=body)

                case LambdaResponseStatusCode.UNPROCESSABLE_ENTITY:
                    raise GlobalRuleUnprocessableEntity(detail=body)

        raise GlobalRuleInternalServerError(detail=body)

    def get_global_rule(self) -> str:
        return self.global_rule_code
