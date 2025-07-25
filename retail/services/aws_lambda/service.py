import logging

from typing import Any, Dict, Optional

from botocore.exceptions import ClientError
from django.core.files.uploadedfile import UploadedFile
from rest_framework.exceptions import APIException

from retail.clients.aws_lambda.client import AwsLambdaClient
from retail.interfaces.clients.aws_lambda.client import AwsLambdaClientInterface
from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface

logger = logging.getLogger(__name__)


class AwsLambdaService(AwsLambdaServiceInterface):
    def __init__(
        self,
        client: Optional[AwsLambdaClientInterface] = None,
        region_name: Optional[str] = None,
    ):
        self.client = client or AwsLambdaClient(region_name=region_name)

    def send_file(self, file_obj: UploadedFile, function_name: str) -> str:
        zip_bytes = file_obj.read()

        try:
            response = self.client.create_function(
                function_name=function_name,
                zip_bytes=zip_bytes,
            )
            logger.info(f"Created Lambda: {function_name}")
            return response["FunctionArn"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceConflictException":
                response = self.client.update_function_code(
                    function_name=function_name,
                    zip_bytes=zip_bytes,
                )
                logger.info(f"Updated Lambda: {function_name}")
                return response["FunctionArn"]

            logger.error(f"Failed to create function in aws lambda: {e}")
            raise APIException("Failed to create function in aws lambda.")

    def invoke(self, function_name: str, payload: dict) -> Dict[str, Any]:
        return self.client.invoke(function_name=function_name, payload=payload)
