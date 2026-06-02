from unittest.mock import MagicMock

from django.test import TestCase

from retail.clients.exceptions import CustomAPIException
from retail.services.slack.service import SlackService


class TestSlackService(TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.service = SlackService(client=self.client)

    def test_send_blocks_delegates_to_client_and_returns_result(self):
        self.client.send_blocks.return_value = True

        result = self.service.send_blocks(channel="#ops", blocks=[{"type": "divider"}])

        self.assertTrue(result)
        self.client.send_blocks.assert_called_once_with(
            channel="#ops", blocks=[{"type": "divider"}]
        )

    def test_send_blocks_returns_false_when_client_raises_custom_api_exception(self):
        self.client.send_blocks.side_effect = CustomAPIException(
            detail="bad request", status_code=400
        )

        result = self.service.send_blocks(channel="#ops", blocks=[])

        self.assertFalse(result)

    def test_send_blocks_returns_false_when_client_raises_unexpected_exception(self):
        self.client.send_blocks.side_effect = RuntimeError("unexpected")

        result = self.service.send_blocks(channel="#ops", blocks=[])

        self.assertFalse(result)

    def test_uses_default_slack_client_when_none_injected(self):
        service = SlackService()

        self.assertIsNotNone(service.client)
