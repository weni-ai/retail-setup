from unittest.mock import MagicMock

from django.test import TestCase, override_settings

from retail.services.notification.contract_acceptance_service import (
    ContractAcceptanceNotificationService,
)


def _acceptance_data(**overrides) -> dict:
    base = {
        "acceptance_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "company_name": "Magazine Luiza S.A.",
        "user_name": "Carlos Eduardo Ferreira",
        "email": "carlos.ferreira@example.com",
        "vtex_account": "magazineluiza",
        "plan": "Até 5.000 conversas",
        "contract_version": "v2.1",
        "accepted_at": "23 de junho de 2026, às 11h32min (UTC-03:00)",
        "geo_country": "BR",
    }
    base.update(overrides)
    return base


@override_settings(SLACK_CONTRACT_ACCEPTANCE_CHANNEL="#contract-acceptances")
class ContractAcceptanceNotificationServiceTests(TestCase):
    def setUp(self):
        self.slack_service = MagicMock()
        self.service = ContractAcceptanceNotificationService(
            slack_service=self.slack_service
        )

    def test_notify_sends_blocks_to_configured_channel(self):
        self.service.notify(_acceptance_data())

        self.slack_service.send_blocks.assert_called_once()
        kwargs = self.slack_service.send_blocks.call_args.kwargs
        self.assertEqual(kwargs["channel"], "#contract-acceptances")
        self.assertIsInstance(kwargs["blocks"], list)

    def test_notify_renders_acceptance_snapshot(self):
        self.service.notify(_acceptance_data())

        serialized = str(self.slack_service.send_blocks.call_args.kwargs["blocks"])
        self.assertIn("magazineluiza", serialized)
        self.assertIn("Magazine Luiza S.A.", serialized)
        self.assertIn("Até 5.000 conversas", serialized)
        self.assertIn("v2.1", serialized)
        self.assertIn("a1b2c3d4-e5f6-7890-abcd-ef1234567890", serialized)

    def test_notify_defaults_geo_country_when_missing(self):
        self.service.notify(_acceptance_data(geo_country=""))

        serialized = str(self.slack_service.send_blocks.call_args.kwargs["blocks"])
        self.assertIn("N/A", serialized)

    @override_settings(SLACK_CONTRACT_ACCEPTANCE_CHANNEL="")
    def test_notify_skips_when_channel_not_configured(self):
        self.service.notify(_acceptance_data())

        self.slack_service.send_blocks.assert_not_called()

    def test_notify_logs_and_swallows_unexpected_errors(self):
        self.slack_service.send_blocks.side_effect = RuntimeError("slack down")

        self.service.notify(_acceptance_data())

        self.slack_service.send_blocks.assert_called_once()
