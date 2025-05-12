from typing import Protocol

from django.core.files.uploadedfile import UploadedFile


class AwsLambdaServiceInterface(Protocol):
    def send_file(self, file_obj: UploadedFile, function_name: str) -> str:
        ...
