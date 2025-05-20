from typing import Protocol, Dict, Any

from django.core.files.uploadedfile import UploadedFile


class AwsLambdaServiceInterface(Protocol):
    def send_file(self, file_obj: UploadedFile, function_name: str) -> str:
        ...

    def invoke(self, function_name: str) -> Dict[str, Any]:
        ...
