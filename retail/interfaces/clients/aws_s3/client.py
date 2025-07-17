from typing import Protocol, runtime_checkable

from django.core.files.uploadedfile import UploadedFile


@runtime_checkable
class S3ClientInterface(Protocol):
    def upload_file(self, file: UploadedFile, key: str) -> str:
        """Uploads a file to an S3 bucket."""
        pass

    def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """Generates a presigned URL for accessing a private S3 object."""
        pass
