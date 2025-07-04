import json

import boto3

from typing import Any, Dict, Optional

from django.conf import settings

from retail.interfaces.clients.aws_lambda.client import AwsLambdaClientInterface


class AwsLambdaClient(AwsLambdaClientInterface):
    def __init__(self, region_name: Optional[str] = None):
        self.boto3_client = boto3.client(
            "lambda", region_name=region_name or settings.LAMBDA_REGION
        )
        self.role_arn = settings.LAMBDA_ROLE_ARN
        self.runtime = settings.LAMBDA_RUNTIME
        self.handler = settings.LAMBDA_HANDLER
        self.timeout = settings.LAMBDA_TIMEOUT

    def create_function(self, function_name: str, zip_bytes: bytes) -> Dict[str, Any]:
        kwargs = {
            "FunctionName": function_name,
            "Runtime": self.runtime,
            "Role": self.role_arn,
            "Handler": self.handler,
            "Code": {"ZipFile": zip_bytes},
            "Timeout": self.timeout,
            "Publish": True,
        }

        return self.boto3_client.create_function(**kwargs)

    def update_function_code(
        self, function_name: str, zip_bytes: bytes
    ) -> Dict[str, Any]:
        return self.boto3_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_bytes,
            Publish=True,
        )

    def invoke(self, function_name: str, payload: dict) -> Dict[str, Any]:
        return self.boto3_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
