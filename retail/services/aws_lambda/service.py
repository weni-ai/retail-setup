import logging

from typing import Optional

from django.core.files.uploadedfile import UploadedFile

from botocore.exceptions import ClientError

from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.interfaces.clients.aws_lambda.client import AwsLambdaClientInterface
from retail.clients.aws_lambda.client import AwsLambdaClient


logger = logging.getLogger(__name__)


class AwsLambdaService(AwsLambdaServiceInterface):
    def __init__(self, client: Optional[AwsLambdaClientInterface] = None):
        self.client = client or AwsLambdaClient()

    def send_file(self, file_obj: UploadedFile, function_name: str) -> str:
        zip_bytes = file_obj.read()

        try:
            response = self.client.create_function(
                function_name=function_name,
                zip_bytes=zip_bytes,
            )
            logger.info(f"Created Lambda: {function_name}")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceConflictException":
                response = self.client.update_function_code(
                    function_name=function_name,
                    zip_bytes=zip_bytes,
                )
            logger.info(f"Updated Lambda: {function_name}")

        return response["FunctionArn"]
