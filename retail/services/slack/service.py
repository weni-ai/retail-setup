import logging
from typing import Optional

from retail.clients.slack.client import SlackClient
from retail.clients.exceptions import CustomAPIException
from retail.interfaces.clients.slack.interface import SlackClientInterface

logger = logging.getLogger(__name__)


class SlackService:
    def __init__(self, client: Optional[SlackClientInterface] = None):
        self.client = client or SlackClient()

    def send_blocks(self, channel: str, blocks: list) -> bool:
        try:
            return self.client.send_blocks(channel=channel, blocks=blocks)
        except CustomAPIException as exc:
            logger.error(f"SlackService: API error: {exc.detail}")
            return False
        except Exception as exc:
            logger.error(f"SlackService: unexpected error: {exc}")
            return False
