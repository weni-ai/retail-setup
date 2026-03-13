"""
Slack API client using chat.postMessage with Block Kit.
"""

import logging

from django.conf import settings

from retail.clients.base import RequestClient
from retail.interfaces.clients.slack.interface import SlackClientInterface

logger = logging.getLogger(__name__)

SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"


class SlackClient(RequestClient, SlackClientInterface):
    def __init__(self):
        self.token = settings.SLACK_BOT_TOKEN
        self.default_channel = settings.SLACK_NOTIFICATION_CHANNEL

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def send_blocks(self, channel: str, blocks: list) -> bool:
        if not self.token:
            logger.warning("Slack bot token not configured, skipping message")
            return False

        target_channel = channel or self.default_channel
        payload = {"channel": target_channel, "blocks": blocks}

        response = self.make_request(
            url=SLACK_POST_MESSAGE_URL,
            method="POST",
            headers=self.headers,
            json=payload,
            timeout=10,
        )

        data = response.json()
        if not data.get("ok"):
            logger.error(
                f"Slack API error: channel={target_channel} "
                f"error={data.get('error')}"
            )
            return False
        return True
