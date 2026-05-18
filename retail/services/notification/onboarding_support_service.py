"""
Notification service for support requests during the onboarding.

The front-end shows a "contact support" screen whenever the onboarding
flow returns an error and the user cannot proceed. When the user clicks
that button, the front-end posts arbitrary diagnostic data to the
support-contact endpoint and this service forwards it — together with a
full snapshot of the current onboarding state — to the dedicated Slack
channel so the team can investigate.

Fail-safe: any error building or sending the notification is logged but
never propagated to the caller — a Slack outage must not prevent the
support request from returning a successful response to the user.
"""

import json
import logging
from typing import Any, Mapping, Optional

from django.conf import settings

from retail.services.slack.service import SlackService

logger = logging.getLogger(__name__)

# Slack section text blocks are capped at 3000 chars. We trim payload
# previews well below that to keep room for the surrounding markdown.
_PAYLOAD_PREVIEW_MAX_CHARS = 2500


class OnboardingSupportNotificationService:
    """Sends onboarding support requests to a dedicated Slack channel."""

    def __init__(self, slack_service: Optional[SlackService] = None):
        self.slack_service = slack_service or SlackService()

    def notify(
        self,
        vtex_account: str,
        data: Optional[Mapping[str, Any]] = None,
        onboarding: Optional[Mapping[str, Any]] = None,
    ) -> None:
        channel = settings.SLACK_ONBOARDING_ERROR_CHANNEL
        if not channel:
            logger.warning(
                "SLACK_ONBOARDING_ERROR_CHANNEL not configured, "
                "skipping onboarding support notification"
            )
            return

        try:
            blocks = self._build_blocks(
                vtex_account=vtex_account,
                data=data,
                onboarding=onboarding,
            )
            self.slack_service.send_blocks(channel=channel, blocks=blocks)
        except Exception:
            logger.exception(
                f"OnboardingSupportNotificationService: failed to send "
                f"notification for vtex_account={vtex_account}"
            )

    def _build_blocks(
        self,
        vtex_account: str,
        data: Optional[Mapping[str, Any]],
        onboarding: Optional[Mapping[str, Any]],
    ) -> list:
        blocks: list = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Onboarding support requested",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "A user has clicked the *Contact support* option "
                        "during the onboarding flow. The full onboarding "
                        "snapshot and the data captured by the front-end "
                        "are included below."
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": self._build_overview_fields(vtex_account, onboarding),
            },
        ]

        ids_block = self._build_ids_block(onboarding)
        if ids_block:
            blocks.append(ids_block)

        reason_block = self._build_reason_block(onboarding)
        if reason_block:
            blocks.append(reason_block)

        config_block = self._build_config_block(onboarding)
        if config_block:
            blocks.append(config_block)

        data_block = self._build_data_block(data)
        if data_block:
            blocks.append(data_block)

        return blocks

    @classmethod
    def _build_overview_fields(
        cls,
        vtex_account: str,
        onboarding: Optional[Mapping[str, Any]],
    ) -> list:
        snapshot = onboarding or {}
        return [
            {"type": "mrkdwn", "text": f"*VTEX Account*\n{vtex_account}"},
            {
                "type": "mrkdwn",
                "text": f"*Project*\n{snapshot.get('project_name') or 'N/A'}",
            },
            {
                "type": "mrkdwn",
                "text": f"*Current Step*\n{snapshot.get('current_step') or 'N/A'}",
            },
            {
                "type": "mrkdwn",
                "text": f"*Current Page*\n{snapshot.get('current_page') or 'N/A'}",
            },
            {
                "type": "mrkdwn",
                "text": f"*Progress*\n{cls._format_progress(snapshot)}",
            },
            {
                "type": "mrkdwn",
                "text": f"*Status*\n{cls._format_status(snapshot)}",
            },
            {
                "type": "mrkdwn",
                "text": (
                    f"*Crawler Result*\n{snapshot.get('crawler_result') or 'N/A'}"
                ),
            },
            {
                "type": "mrkdwn",
                "text": f"*Created On*\n{snapshot.get('created_on') or 'N/A'}",
            },
        ]

    @staticmethod
    def _build_ids_block(
        onboarding: Optional[Mapping[str, Any]],
    ) -> Optional[dict]:
        if not onboarding:
            return None
        onboarding_uuid = onboarding.get("uuid")
        project_uuid = onboarding.get("project_uuid")
        if not onboarding_uuid and not project_uuid:
            return None
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Onboarding UUID*: `{onboarding_uuid or 'N/A'}`\n"
                    f"*Project UUID*: `{project_uuid or 'N/A'}`"
                ),
            },
        }

    @classmethod
    def _build_reason_block(
        cls,
        onboarding: Optional[Mapping[str, Any]],
    ) -> Optional[dict]:
        config = (onboarding or {}).get("config") or {}
        reason = config.get("reason_failed")
        if not reason:
            return None
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Last recorded failure*\n```{cls._truncate(reason)}```",
            },
        }

    @classmethod
    def _build_config_block(
        cls,
        onboarding: Optional[Mapping[str, Any]],
    ) -> Optional[dict]:
        config = (onboarding or {}).get("config")
        config_preview = cls._format_json_preview(config)
        if not config_preview:
            return None
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Onboarding config*\n```{config_preview}```",
            },
        }

    @classmethod
    def _build_data_block(
        cls,
        data: Optional[Mapping[str, Any]],
    ) -> Optional[dict]:
        data_preview = cls._format_json_preview(data)
        if not data_preview:
            return None
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Front-end payload*\n```{data_preview}```",
            },
        }

    @staticmethod
    def _format_progress(snapshot: Mapping[str, Any]) -> str:
        progress = snapshot.get("progress")
        if progress is None:
            return "N/A"
        return f"{progress}%"

    @staticmethod
    def _format_status(snapshot: Mapping[str, Any]) -> str:
        if not snapshot:
            return "N/A"
        flags = []
        if snapshot.get("completed"):
            flags.append("completed")
        if snapshot.get("failed"):
            flags.append("failed")
        if snapshot.get("skipped"):
            flags.append("skipped")
        return ", ".join(flags) if flags else "in progress"

    @classmethod
    def _format_json_preview(cls, value: Optional[Mapping[str, Any]]) -> str:
        if not value:
            return ""
        try:
            serialized = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):
            serialized = str(value)
        return cls._truncate(serialized)

    @staticmethod
    def _truncate(text: str) -> str:
        if len(text) <= _PAYLOAD_PREVIEW_MAX_CHARS:
            return text
        return text[:_PAYLOAD_PREVIEW_MAX_CHARS] + "\n... [truncated]"
