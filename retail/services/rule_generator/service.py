import json

import logging

import time

from typing import Optional, Dict, Any, List

from enum import IntEnum

from django.conf import settings

from rest_framework.exceptions import APIException
from rest_framework import status

from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.services.aws_lambda import AwsLambdaService
from retail.agents.domains.agent_integration.models import IntegratedAgent


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


logger = logging.getLogger(__name__)


class RuleGenerator:
    """Handles code generation using AWS Lambda service with retry mechanism"""

    def __init__(
        self,
        lambda_service: Optional[AwsLambdaServiceInterface] = None,
        max_retry_attempts: int = 1,
        retry_delay_seconds: float = 1.0,
    ):
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
        self.max_retry_attempts = max_retry_attempts
        self.retry_delay_seconds = retry_delay_seconds

    def generate_code(
        self,
        parameters: List[Dict[str, Any]],
        integrated_agent: Optional[IntegratedAgent] = None,
    ) -> str:
        """
        Generate code using Lambda service with retry mechanism

        Args:
            parameters: List of parameters for code generation
            integrated_agent: Optional integrated agent for adding examples

        Returns:
            str: Generated code
        """
        return self._generate_code_with_retry(parameters, integrated_agent)

    def _generate_code_with_retry(
        self,
        parameters: List[Dict[str, Any]],
        integrated_agent: Optional[IntegratedAgent] = None,
    ) -> str:
        """
        Generate code with retry mechanism for non-success responses

        Args:
            parameters: List of parameters for code generation
            integrated_agent: Optional integrated agent for adding examples

        Returns:
            str: Generated code

        Raises:
            Exception: Last exception encountered if all retry attempts fail
        """
        last_exception = None

        for attempt in range(self.max_retry_attempts + 1):
            try:
                logger.info(
                    f"Code generation attempt {attempt + 1}/{self.max_retry_attempts + 1}"
                )

                response_payload = self._invoke_code_generator(
                    parameters, integrated_agent
                )
                result = self._handle_response(response_payload)

                if attempt > 0:
                    logger.info(f"Code generation succeeded on attempt {attempt + 1}")

                return result

            except (
                RuleGeneratorBadRequest,
                RuleGeneratorUnprocessableEntity,
                RuleGeneratorInternalServerError,
            ) as e:
                last_exception = e

                if attempt < self.max_retry_attempts:
                    logger.warning(
                        f"Code generation failed on attempt {attempt + 1}: {str(e)}. "
                        f"Retrying in {self.retry_delay_seconds} seconds..."
                    )
                    time.sleep(self.retry_delay_seconds)
                else:
                    logger.error(
                        f"Code generation failed after {self.max_retry_attempts + 1} attempts. "
                        f"Final error: {str(e)}"
                    )

        raise last_exception

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
