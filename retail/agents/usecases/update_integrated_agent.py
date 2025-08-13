import json

from typing import TypedDict, Optional, Dict, Any

from enum import IntEnum

from rest_framework.exceptions import NotFound, ValidationError, APIException

from django.conf import settings

from uuid import UUID

from retail.agents.models import IntegratedAgent
from retail.agents.exceptions import (
    GlobalRuleBadRequest,
    GlobalRuleInternalServerError,
    GlobalRuleUnprocessableEntity,
)
from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService


class UpdateIntegratedAgentData(TypedDict):
    contact_percentage: Optional[int]
    global_rule: Optional[str]


class LambdaResponseStatusCode(IntEnum):
    OK = 200
    BAD_REQUEST = 400
    UNPROCESSABLE_ENTITY = 422


class GlobalRuleHandler:
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
    ) -> "GlobalRuleHandler":
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

    def validate(self) -> "GlobalRuleHandler":
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


class UpdateIntegratedAgentUseCase:
    def __init__(self, global_rule_handler: Optional[GlobalRuleHandler] = None):
        self.global_rule_handler = global_rule_handler or GlobalRuleHandler()

    def get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        try:
            return IntegratedAgent.objects.get(
                uuid=integrated_agent_uuid, is_active=True
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found {integrated_agent_uuid}")

    def _is_valid_percentage(self, percentage: int) -> bool:
        return 0 <= percentage <= 100

    def execute(
        self, integrated_agent: IntegratedAgent, data: UpdateIntegratedAgentData
    ) -> IntegratedAgent:

        if "contact_percentage" in data:
            contact_percentage = data.get("contact_percentage")

            if not self._is_valid_percentage(contact_percentage):
                raise ValidationError({"contact_percentage": "Invalid percentage"})

            integrated_agent.contact_percentage = contact_percentage

        if "global_rule" in data:
            global_rule = data.get("global_rule")

            if global_rule is None or global_rule == "":
                global_rule_code = None
                global_rule_prompt = None
            else:
                global_rule_code = (
                    self.global_rule_handler.generate(integrated_agent, global_rule)
                    .validate()
                    .get_global_rule()
                )
                global_rule_prompt = global_rule

            integrated_agent.global_rule_code = global_rule_code
            integrated_agent.global_rule_prompt = global_rule_prompt

        integrated_agent.save()
        return integrated_agent
