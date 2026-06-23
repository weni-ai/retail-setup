"""
Slack notification for self-serve VTEX CX contract acceptances.

Fail-safe: Slack outages or misconfiguration must never block or roll
back the legal acceptance record.
"""

import logging
from typing import Mapping, Optional

from django.conf import settings

from retail.services.slack.service import SlackService

logger = logging.getLogger(__name__)

CONTRACT_ACCEPTANCE_SOURCE = "app auto service"


class ContractAcceptanceNotificationService:
    """Notifies the internal team when a customer accepts the contract."""

    def __init__(self, slack_service: Optional[SlackService] = None):
        self.slack_service = slack_service or SlackService()

    def notify(self, acceptance_data: Mapping[str, str]) -> None:
        channel = settings.SLACK_CONTRACT_ACCEPTANCE_CHANNEL
        if not channel:
            logger.warning("SLACK_CONTRACT_ACCEPTANCE_CHANNEL not configured, skipping")
            return

        try:
            blocks = self._build_blocks(acceptance_data)
            self.slack_service.send_blocks(channel=channel, blocks=blocks)
        except Exception:
            logger.exception(
                "ContractAcceptanceNotificationService: failed to send "
                f"notification for vtex_account="
                f"{acceptance_data.get('vtex_account', 'unknown')}"
            )

    @staticmethod
    def _build_blocks(acceptance_data: Mapping[str, str]) -> list:
        geo_country = acceptance_data.get("geo_country") or "N/A"

        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "New VTEX CX contract acceptance",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "A customer has completed the self-serve contract "
                        "acceptance flow."
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*from*\n{CONTRACT_ACCEPTANCE_SOURCE}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Company*\n{acceptance_data['company_name']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*vtex_account*\n{acceptance_data['vtex_account']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Responsible user*\n{acceptance_data['user_name']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Email*\n{acceptance_data['email']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Plan*\n{acceptance_data['plan']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"*Contract version*\n"
                            f"{acceptance_data['contract_version']}"
                        ),
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Country*\n{geo_country}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Accepted at*\n{acceptance_data['accepted_at']}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (f"*Acceptance ID*\n`{acceptance_data['acceptance_id']}`"),
                },
            },
        ]
