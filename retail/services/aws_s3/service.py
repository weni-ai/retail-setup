from typing import Optional

from django.core.files.uploadedfile import UploadedFile

from retail.interfaces.clients.aws_s3.client import S3ClientInterface
from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.clients.aws_s3.client import S3Client

from retail.services.aws_s3.converters import Base64ToUploadedFileConverter


class S3Service(S3ServiceInterface):
    def __init__(self, client: Optional[S3ClientInterface] = None):
        self.client = client or S3Client()
        self.base_64_converter = Base64ToUploadedFileConverter()

    def upload_file(self, file: UploadedFile, key: str) -> str:
        """Uploads a file to an S3 bucket and returns the key."""
        return self.client.upload_file(file, key)

    def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """Generates a presigned URL for accessing a private S3 object."""
        return self.client.generate_presigned_url(key, expiration)
