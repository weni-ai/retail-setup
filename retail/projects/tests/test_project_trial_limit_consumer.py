import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.consumers.project_trial_limit_consumer import (
    ProjectTrialLimitConsumer,
)


class TestProjectTrialLimitConsumer(TestCase):
    def setUp(self):
        self.consumer = ProjectTrialLimitConsumer()
        self.project_uuid = str(uuid4())

    def _call_handle(self, body: dict):
        """Calls handle() with mocked pika args, returning the mock channel."""
        channel = MagicMock()
        method = MagicMock()
        method.delivery_tag = "tag-1"
        properties = MagicMock()
        raw_body = json.dumps(body).encode("utf-8")
        self.consumer.handle(channel, method, properties, raw_body)
        return channel

    @patch(
        "retail.projects.consumers.project_trial_limit_consumer"
        ".SuspendTrialProjectUseCase"
    )
    def test_delegates_to_use_case_with_correct_dto(self, mock_use_case_cls):
        mock_use_case = MagicMock()
        mock_use_case_cls.return_value = mock_use_case

        channel = self._call_handle(
            {
                "project_uuid": self.project_uuid,
                "conversation_limit": 1000,
            }
        )

        mock_use_case.execute.assert_called_once()
        dto = mock_use_case.execute.call_args[0][0]
        self.assertEqual(dto.project_uuid, self.project_uuid)
        self.assertEqual(dto.conversation_limit, 1000)
        channel.basic_ack.assert_called_once_with("tag-1")

    @patch(
        "retail.projects.consumers.project_trial_limit_consumer"
        ".SuspendTrialProjectUseCase"
    )
    def test_rejects_message_on_use_case_failure(self, mock_use_case_cls):
        mock_use_case = MagicMock()
        mock_use_case.execute.side_effect = Exception("Something went wrong")
        mock_use_case_cls.return_value = mock_use_case

        channel = self._call_handle(
            {
                "project_uuid": self.project_uuid,
                "conversation_limit": 1000,
            }
        )

        channel.basic_reject.assert_called_once_with("tag-1", requeue=False)
        channel.basic_ack.assert_not_called()

    @patch(
        "retail.projects.consumers.project_trial_limit_consumer"
        ".SuspendTrialProjectUseCase"
    )
    def test_handles_different_conversation_limits(self, mock_use_case_cls):
        mock_use_case = MagicMock()
        mock_use_case_cls.return_value = mock_use_case

        self._call_handle(
            {
                "project_uuid": self.project_uuid,
                "conversation_limit": 2000,
            }
        )

        dto = mock_use_case.execute.call_args[0][0]
        self.assertEqual(dto.conversation_limit, 2000)
