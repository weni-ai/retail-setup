from typing import Protocol

from django.core.files.uploadedfile import UploadedFile


class S3ServiceInterface(Protocol):
    def upload_file(self, file: UploadedFile, key: str) -> str:
        """Uploads a file to an S3 bucket."""
        pass
