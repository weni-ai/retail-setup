import boto3

from django.conf import settings

from typing import Dict, Any

from retail.interfaces.clients.aws_lambda.client import AwsLambdaClientInterface


class AwsLambdaClient(AwsLambdaClientInterface):
    def __init__(self):
        self.boto3_client = boto3.client("lambda")
        self.role_arn = settings.LAMBDA_ROLE_ARN
        self.handler = settings.LAMBDA_HANDLER
        self.runtime = settings.LAMBDA_RUNTIME

    def create_function(self, function_name: str, zip_bytes: bytes) -> Dict[str, Any]:
        kwargs = {
            "FunctionName": function_name,
            "Runtime": self.runtime,
            "Role": self.role_arn,
            "Handler": self.handler,
            "Code": {"ZipFile": zip_bytes},
            "Publish": True,
        }

        return self.boto3_client.create_function(**kwargs)
