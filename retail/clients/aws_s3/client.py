import boto3

from typing import Optional

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from retail.interfaces.clients.aws_s3.client import S3ClientInterface


class S3Client(S3ClientInterface):
    def __init__(self, bucket_name: Optional[str] = None):
        self.s3 = boto3.client("s3")
        self.bucket_name = bucket_name or settings.AWS_STORAGE_BUCKET_NAME

    def upload_file(self, file: UploadedFile, key: str) -> str:
        """Uploads a file to an S3 bucket."""
        self.s3.upload_fileobj(file, self.bucket_name, key)
        return f"s3://{self.bucket_name}/{key}"
