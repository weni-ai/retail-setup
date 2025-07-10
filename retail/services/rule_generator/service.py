import json

from typing import Optional, Dict, Any, List
from enum import IntEnum

from django.conf import settings

from rest_framework.exceptions import APIException
from rest_framework import status

from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.agents.models import IntegratedAgent


class RuleGeneratorBadRequest(APIException):
    status_code = status.HTTP_400_BAD_REQUEST


class RuleGeneratorUnprocessableEntity(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class RuleGeneratorInternalServerError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class RuleGeneratorResponseStatusCode(IntEnum):
    OK = 200
    BAD_REQUEST = 400
    UNPROCESSABLE_ENTITY = 422


class RuleGenerator:
    """Handles code generation using AWS Lambda service"""

    def __init__(self, lambda_service: Optional[AwsLambdaServiceInterface] = None):
        self.lambda_service = lambda_service or AwsLambdaService(
            region_name=getattr(
                settings,
                "LAMBDA_CODE_GENERATOR_REGION",
                "us-east-1",
            )
        )
        self.lambda_code_generator = getattr(
            settings,
            "LAMBDA_CODE_GENERATOR",
            "arn:aws:lambda:us-east-1:123456789012:function:mock",
        )

    def generate_code(
        self,
        parameters: List[Dict[str, Any]],
        integrated_agent: Optional[IntegratedAgent] = None,
    ) -> str:
        """
        Generate code using Lambda service

        Args:
            parameters: List of parameters for code generation
            integrated_agent: Optional integrated agent for adding examples

        Returns:
            str: Generated code
        """
        response_payload = self._invoke_code_generator(parameters, integrated_agent)
        return self._handle_response(response_payload)

    def _invoke_code_generator(
        self,
        params: List[Dict[str, Any]],
        integrated_agent: Optional[IntegratedAgent] = None,
    ) -> Dict[str, Any]:
        """Invoke Lambda code generator"""
        if integrated_agent:
            example_parameter = {
                "name": "examples",
                "value": integrated_agent.agent.examples,
            }
            params.append(example_parameter)

        payload = {"parameters": params}

        response = self.lambda_service.invoke(
            function_name=self.lambda_code_generator, payload=payload
        )

        return json.loads(response["Payload"].read())

    def _handle_response(self, response_payload: Dict[str, Any]) -> str:
        """Handle Lambda response and raise appropriate exceptions"""
        status_code = response_payload.get("statusCode")
        body = response_payload.get("body")

        if status_code is not None:
            match status_code:
                case RuleGeneratorResponseStatusCode.OK:
                    return body.get("generated_code", "")
                case RuleGeneratorResponseStatusCode.BAD_REQUEST:
                    raise RuleGeneratorBadRequest(detail=body)
                case RuleGeneratorResponseStatusCode.UNPROCESSABLE_ENTITY:
                    raise RuleGeneratorUnprocessableEntity(detail=body)

        raise RuleGeneratorInternalServerError(
            detail={"message": "Unknown error from lambda.", "error": response_payload}
        )
