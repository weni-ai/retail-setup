import boto3

from typing import Dict, Any

from retail.interfaces.clients.aws_lambda.client import AwsLambdaClientInterface


class AwsLambdaClient(AwsLambdaClientInterface):
    def __init__(self):
        self.boto3_client = boto3.client("lambda")

    def invoke(self, function_name: str, payload: bytes) -> Dict[str, Any]:
        response = self.boto3_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=payload,
        )
        return response
