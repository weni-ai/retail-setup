import boto3

import logging

from typing import Optional

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from retail.interfaces.clients.aws_s3.client import S3ClientInterface

logger = logging.getLogger(__name__)


class S3Client(S3ClientInterface):
    def __init__(self, bucket_name: Optional[str] = None):
        try:
            sts_client = boto3.client("sts")
            assumed_role = sts_client.assume_role(
                RoleArn=settings.AWS_STORAGE_ROLE, RoleSessionName="S3ClientSession"
            )
            credentials = assumed_role["Credentials"]

            self.s3 = boto3.client(
                "s3",
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )

            logger.info("S3Client configured successfully")

        except Exception as e:
            logger.error(f"Error assuming role {settings.AWS_STORAGE_ROLE}: {e}")

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
