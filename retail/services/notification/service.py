"""
Notification service for lead events.

Builds Slack Block Kit message and sends to the configured channel.
"""

import logging
from typing import Optional

from django.conf import settings

from retail.services.slack.service import SlackService

logger = logging.getLogger(__name__)


class LeadNotificationService:
    def __init__(self, slack_service: Optional[SlackService] = None):
        self.slack_service = slack_service or SlackService()

    def notify(self, lead_data: dict) -> None:
        blocks = self._build_blocks(lead_data)
        channel = settings.SLACK_LEAD_NOTIFICATION_CHANNEL
        if not channel:
            logger.warning("SLACK_LEAD_NOTIFICATION_CHANNEL not configured, skipping")
            return
        self.slack_service.send_blocks(channel=channel, blocks=blocks)

    def _build_blocks(self, lead_data: dict) -> list:
        metrics = lead_data.get("data", {})

        carts_triggered = metrics.get("carts_triggered", "N/A")
        carts_converted = metrics.get("carts_converted", "N/A")
        total_conversations = metrics.get("total_conversations", "N/A")
        csat = metrics.get("csat", "N/A")
        resolution_rate = metrics.get("resolution_rate", "N/A")

        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "\U0001f680 New Plan Interest Detected",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*User Email*\n{lead_data['user_email']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*VTEX Account*\n{lead_data['vtex_account']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Country*\n{lead_data['region'] or 'N/A'}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Date & Time*\n{lead_data['date']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Plan*\n{lead_data['plan']}",
                    },
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*\U0001f6d2 Abandoned Cart Automation*",
                },
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Carts Triggered*\n{carts_triggered}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Carts Converted*\n{carts_converted}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*\U0001f4ac Conversation Metrics*",
                },
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Total Conversations*\n{total_conversations}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Customer Satisfaction (CSAT)*\n{csat}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Resolution Rate*\n{resolution_rate}",
                    },
                ],
            },
        ]
