import boto3

import mimetypes

import logging

from typing import Optional

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from retail.interfaces.clients.aws_s3.client import S3ClientInterface

logger = logging.getLogger(__name__)


class S3Client(S3ClientInterface):
    def __init__(self, bucket_name: Optional[str] = None):
        self.s3 = boto3.client("s3")
        self.bucket_name = bucket_name or getattr(
            settings, "AWS_STORAGE_BUCKET_NAME", "test-bucket"
        )

    def upload_file(self, file: UploadedFile, key: str) -> str:
        """Uploads a file to an S3 bucket and returns the key."""
        content_type = getattr(file, "content_type", None)

        if not content_type:
            content_type, _ = mimetypes.guess_type(file.name)

        if not content_type:
            content_type = "application/octet-stream"

        extra_args = {
            "ContentType": content_type,
        }

        if content_type.startswith("image/"):
            extra_args["ContentDisposition"] = "inline"

        logger.info(f"Uploading file {key} with content_type: {content_type}")

        self.s3.upload_fileobj(file, self.bucket_name, key, ExtraArgs=extra_args)

        return key

    def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """Generates a presigned URL for accessing a private S3 object."""
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": key},
            ExpiresIn=expiration,
        )
