import boto3

from typing import Optional

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from retail.interfaces.clients.aws_s3.client import S3ClientInterface


class S3Client(S3ClientInterface):
    def __init__(self, bucket_name: Optional[str] = None):
        self.s3 = boto3.client("s3")
        self.bucket_name = bucket_name or getattr(
            settings, "AWS_STORAGE_BUCKET_NAME", "test-bucket"
        )

    def upload_file(self, file: UploadedFile, key: str) -> str:
        """Uploads a file to an S3 bucket and returns the key."""
        self.s3.upload_fileobj(file, self.bucket_name, key)
        return key

    def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """Generates a presigned URL for accessing a private S3 object."""
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": key},
            ExpiresIn=expiration,
        )
