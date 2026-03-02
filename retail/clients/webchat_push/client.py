import boto3
import logging

from typing import Optional

from django.conf import settings

from retail.interfaces.clients.webchat_push.client import WebchatPushClientInterface

logger = logging.getLogger(__name__)


class WebchatPushClient(WebchatPushClientInterface):
    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
    ):
        self.bucket_name = bucket_name or settings.WEBCHAT_PUSH_S3_BUCKET_NAME
        region = region or settings.WEBCHAT_PUSH_S3_REGION
        access_key_id = access_key_id or settings.WEBCHAT_PUSH_S3_ACCESS_KEY_ID
        secret_access_key = (
            secret_access_key or settings.WEBCHAT_PUSH_S3_SECRET_ACCESS_KEY
        )

        self.s3 = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def upload_script(self, key: str, script_content: str, redirect_url: str) -> str:
        """Uploads a webchat loader script to S3 with a website redirect header."""
        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=script_content.encode("utf-8"),
            ContentType="application/javascript",
            WebsiteRedirectLocation=redirect_url,
        )

        logger.info(f"Uploaded webchat script to s3://{self.bucket_name}/{key}")
        return f"https://{self.bucket_name}.s3.amazonaws.com/{key}"
