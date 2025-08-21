import json

import logging

from enum import IntEnum

from typing import Any, Dict, Optional


from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.interfaces.jwt import JWTInterface
from retail.jwt_keys.usecases.generate_jwt import JWTUsecase
from retail.services.aws_lambda import AwsLambdaService
from retail.interfaces.clients.aws_lambda.client import RequestData

logger = logging.getLogger(__name__)


class ActiveAgentResponseStatus(IntEnum):
    """Enum for possible Lambda response statuses."""

    RULE_MATCHED = 0
    RULE_NOT_MATCHED = 1
    PRE_PROCESSING_FAILED = 2
    CUSTOM_RULE_FAILED = 3
    OFFICIAL_RULE_FAILED = 4
    GLOBAL_RULE_FAILED = 5
    GLOBAL_RULE_NOT_MATCHED = 6


class ActiveAgent:
    def __init__(
        self,
        lambda_service: Optional[AwsLambdaServiceInterface] = None,
        jwt_generator: Optional[JWTInterface] = None,
    ):
        self.lambda_service = lambda_service or AwsLambdaService()
        self.jwt_generator = jwt_generator or JWTUsecase()

    def invoke(
        self, integrated_agent: IntegratedAgent, data: "RequestData"
    ) -> Dict[str, Any]:
        """Invoke lambda function with agent and request data."""
        function_name = integrated_agent.agent.lambda_arn
        project = integrated_agent.project
        jwt_token = self.jwt_generator.generate_jwt_token(str(project.uuid))
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
                    "auth_token": jwt_token,
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
                case ActiveAgentResponseStatus.RULE_MATCHED:
                    return True
                case ActiveAgentResponseStatus.RULE_NOT_MATCHED:
                    logger.info(
                        f"Rule not matched for integrated agent {integrated_agent.uuid}: {error}"
                    )
                    return False
                case ActiveAgentResponseStatus.PRE_PROCESSING_FAILED:
                    logger.info(
                        f"Pre-processing failed for integrated agent {integrated_agent.uuid}: {error}"
                    )
                    return False
                case ActiveAgentResponseStatus.CUSTOM_RULE_FAILED:
                    logger.info(
                        f"Custom rule failed for integrated agent {integrated_agent.uuid}: {error}"
                    )
                    return False
                case ActiveAgentResponseStatus.OFFICIAL_RULE_FAILED:
                    logger.info(
                        f"Official rule failed for integrated agent {integrated_agent.uuid}: {error}"
                    )
                    return False
                case ActiveAgentResponseStatus.GLOBAL_RULE_FAILED:
                    logger.info(
                        f"Global rule failed for integrated agent {integrated_agent.uuid}: {error}"
                    )
                    return False
                case ActiveAgentResponseStatus.GLOBAL_RULE_NOT_MATCHED:
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
