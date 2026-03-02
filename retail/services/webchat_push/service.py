import os
import logging

from typing import Optional

from django.conf import settings

from retail.interfaces.clients.webchat_push.client import WebchatPushClientInterface
from retail.clients.webchat_push.client import WebchatPushClient

logger = logging.getLogger(__name__)


class WebchatPushService:
    def __init__(self, client: Optional[WebchatPushClientInterface] = None):
        self.client = client or WebchatPushClient()

    def _build_loader_script(self, script_url: str) -> str:
        loader_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "loader.script"
        )

        with open(loader_path, "r") as f:
            template = f.read()

        template = template.replace("<CDN_URL>", settings.WEBCHAT_CDN_URL)
        template = template.replace("<SCRIPT_URL>", script_url)
        return template

    def publish_webchat_script(self, script_url: str, account_id: str) -> str:
        """
        Builds the webchat loader script and uploads it to the push-webchat bucket.

        Raises:
            WebchatPublishError: If the upload to S3 fails.
        """
        loader_script = self._build_loader_script(script_url)
        key = f"VTEXApp/accounts/{account_id}/webchat.js"

        try:
            uploaded_url = self.client.upload_script(
                key=key,
                script_content=loader_script,
                redirect_url=script_url,
            )
        except Exception as exc:
            logger.error(
                f"Failed to upload webchat script for account_id={account_id}: {exc}"
            )
            raise WebchatPublishError(
                f"Could not upload webchat script: {exc}"
            ) from exc

        logger.info(f"Published webchat script at {uploaded_url}")
        return uploaded_url


class WebchatPublishError(Exception):
    """Raised when the webchat script cannot be published to S3."""
