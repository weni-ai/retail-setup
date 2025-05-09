import json
import base64
import io
import zipfile

from typing import Optional, Dict, Any

from retail.interfaces.services.aws_lambda import AwsLambdaServiceInterface
from retail.interfaces.clients.aws_lambda.client import AwsLambdaClientInterface
from retail.clients.aws_lambda.client import AwsLambdaClient


class AwsLambdaService(AwsLambdaServiceInterface):
    def __init__(
        self, function_name: str, client: Optional[AwsLambdaClientInterface] = None
    ):
        self.client = client or AwsLambdaClient()
        self.function_name = function_name

    def send_file(
        self, file_obj: bytes, extra_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(file_obj.name, file_obj.read())

        zip_buffer.seek(0)
        zip_content = zip_buffer.read()

        zip_base64 = base64.b64encode(zip_content).decode("utf-8")

        payload = {
            "filename": f"{file_obj.name}.zip",
            "content": zip_base64,
        }

        if extra_data:
            payload.update(extra_data)

        payload_bytes = json.dumps(payload).encode("utf-8")

        response = self.lambda_client.invoke(self.function_name, payload_bytes)

        return response
