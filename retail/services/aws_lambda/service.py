from typing import Optional

from django.core.files.uploadedfile import UploadedFile

from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.interfaces.clients.aws_lambda.client import AwsLambdaClientInterface
from retail.clients.aws_lambda.client import AwsLambdaClient


class AwsLambdaService(AwsLambdaServiceInterface):
    def __init__(self, client: Optional[AwsLambdaClientInterface] = None):
        self.client = client or AwsLambdaClient()

    def send_file(self, file_obj: UploadedFile, function_name: str) -> str:
        zip_bytes = file_obj.read()

        response = self.client.create_function(
            function_name=function_name,
            zip_bytes=zip_bytes,
        )

        return response["FunctionArn"]
