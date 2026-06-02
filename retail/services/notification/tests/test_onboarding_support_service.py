from unittest.mock import MagicMock

from django.test import TestCase, override_settings

from retail.services.notification.onboarding_support_service import (
    OnboardingSupportNotificationService,
)


def _snapshot(**overrides) -> dict:
    base = {
        "uuid": "onboarding-uuid",
        "project_name": "My Store",
        "project_uuid": "project-uuid",
        "current_step": "CRAWL",
        "current_page": "setup_channel",
        "progress": 42,
        "completed": False,
        "failed": True,
        "skipped": False,
        "crawler_result": "FAIL",
        "created_on": "2026-05-18T10:00:00+00:00",
        "config": {"reason_failed": "Crawler offline", "channels": {"wwc": {}}},
    }
    base.update(overrides)
    return base


@override_settings(SLACK_ONBOARDING_ERROR_CHANNEL="#onboarding-errors")
class TestOnboardingSupportNotificationService(TestCase):
    def setUp(self):
        self.slack_service = MagicMock()
        self.service = OnboardingSupportNotificationService(
            slack_service=self.slack_service
        )

    def test_notify_sends_blocks_to_configured_channel(self):
        self.service.notify(vtex_account="mystore")

        self.slack_service.send_blocks.assert_called_once()
        kwargs = self.slack_service.send_blocks.call_args.kwargs
        self.assertEqual(kwargs["channel"], "#onboarding-errors")
        self.assertIsInstance(kwargs["blocks"], list)
        self.assertGreater(len(kwargs["blocks"]), 0)

    def test_notify_renders_full_onboarding_snapshot(self):
        self.service.notify(
            vtex_account="mystore",
            onboarding=_snapshot(),
        )

        serialized = str(self.slack_service.send_blocks.call_args.kwargs["blocks"])
        self.assertIn("mystore", serialized)
        self.assertIn("My Store", serialized)
        self.assertIn("CRAWL", serialized)
        self.assertIn("setup_channel", serialized)
        self.assertIn("42%", serialized)
        self.assertIn("failed", serialized)
        self.assertIn("FAIL", serialized)
        self.assertIn("2026-05-18T10:00:00+00:00", serialized)
        self.assertIn("onboarding-uuid", serialized)
        self.assertIn("project-uuid", serialized)

    def test_notify_includes_reason_failed_when_present_in_config(self):
        self.service.notify(
            vtex_account="mystore",
            onboarding=_snapshot(config={"reason_failed": "Crawler offline"}),
        )

        serialized = str(self.slack_service.send_blocks.call_args.kwargs["blocks"])
        self.assertIn("Last recorded failure", serialized)
        self.assertIn("Crawler offline", serialized)

    def test_notify_includes_config_block_when_config_not_empty(self):
        self.service.notify(
            vtex_account="mystore",
            onboarding=_snapshot(
                config={"channels": {"wpp-cloud": {"app_uuid": "abc"}}}
            ),
        )

        serialized = str(self.slack_service.send_blocks.call_args.kwargs["blocks"])
        self.assertIn("Onboarding config", serialized)
        self.assertIn("app_uuid", serialized)

    def test_notify_renders_in_progress_status_when_no_flags_set(self):
        self.service.notify(
            vtex_account="mystore",
            onboarding=_snapshot(
                completed=False, failed=False, skipped=False, config={}
            ),
        )

        serialized = str(self.slack_service.send_blocks.call_args.kwargs["blocks"])
        self.assertIn("in progress", serialized)

    def test_notify_includes_front_end_payload_section(self):
        self.service.notify(
            vtex_account="mystore",
            data={"message": "I cannot proceed", "screen": "channel_setup"},
        )

        serialized = str(self.slack_service.send_blocks.call_args.kwargs["blocks"])
        self.assertIn("Front-end payload", serialized)
        self.assertIn("I cannot proceed", serialized)
        self.assertIn("channel_setup", serialized)

    def test_notify_renders_na_overview_when_onboarding_is_none(self):
        self.service.notify(vtex_account="mystore", onboarding=None)

        serialized = str(self.slack_service.send_blocks.call_args.kwargs["blocks"])
        self.assertIn("mystore", serialized)
        self.assertIn("N/A", serialized)
        self.assertNotIn("Onboarding config", serialized)
        self.assertNotIn("Last recorded failure", serialized)
        self.assertNotIn("Onboarding UUID", serialized)

    def test_notify_truncates_large_config_blob(self):
        huge_config = {"big": "x" * 10000}

        self.service.notify(
            vtex_account="mystore",
            onboarding=_snapshot(config=huge_config),
        )

        serialized = str(self.slack_service.send_blocks.call_args.kwargs["blocks"])
        self.assertIn("[truncated]", serialized)

    def test_notify_status_reports_all_active_flags(self):
        self.service.notify(
            vtex_account="mystore",
            onboarding=_snapshot(completed=True, failed=True, skipped=True),
        )

        serialized = str(self.slack_service.send_blocks.call_args.kwargs["blocks"])
        self.assertIn("completed", serialized)
        self.assertIn("failed", serialized)
        self.assertIn("skipped", serialized)

    def test_notify_omits_ids_block_when_snapshot_has_no_uuids(self):
        self.service.notify(
            vtex_account="mystore",
            onboarding={"current_step": "CRAWL"},
        )

        serialized = str(self.slack_service.send_blocks.call_args.kwargs["blocks"])
        self.assertNotIn("Onboarding UUID", serialized)

    def test_notify_falls_back_to_str_when_json_serialization_fails(self):
        circular: dict = {}
        circular["self"] = circular

        self.service.notify(vtex_account="mystore", data=circular)

        self.slack_service.send_blocks.assert_called_once()

    def test_notify_does_not_propagate_when_send_blocks_raises(self):
        self.slack_service.send_blocks.side_effect = RuntimeError("slack down")

        self.service.notify(vtex_account="mystore")

        self.slack_service.send_blocks.assert_called_once()


class TestOnboardingSupportNotificationServiceWithoutChannel(TestCase):
    @override_settings(SLACK_ONBOARDING_ERROR_CHANNEL="")
    def test_notify_skips_when_channel_not_configured(self):
        slack_service = MagicMock()
        service = OnboardingSupportNotificationService(slack_service=slack_service)

        service.notify(vtex_account="mystore")

        slack_service.send_blocks.assert_not_called()
