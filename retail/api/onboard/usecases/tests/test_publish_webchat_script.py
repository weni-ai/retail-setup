from unittest.mock import MagicMock

from django.test import TestCase
from rest_framework.exceptions import APIException, ValidationError

from retail.api.onboard.usecases.dto import ActivateWebchatDTO
from retail.api.onboard.usecases.publish_webchat_script import (
    PublishWebchatResult,
    PublishWebchatScriptUseCase,
)
from retail.services.webchat_push.service import WebchatPublishError


class TestPublishWebchatScriptUseCase(TestCase):
    def setUp(self):
        self.integrations_service = MagicMock()
        self.webchat_push_service = MagicMock()
        self.usecase = PublishWebchatScriptUseCase(
            integrations_service=self.integrations_service,
            webchat_push_service=self.webchat_push_service,
        )
        self.dto = ActivateWebchatDTO(
            app_uuid="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            account_id="b1165658e9e54790881952eb99341e51",
        )

    def test_execute_success(self):
        self.integrations_service.get_channel_app.return_value = {
            "config": {"script": "https://example.com/wwc.js"}
        }
        self.webchat_push_service.publish_webchat_script.return_value = (
            "https://bucket.s3.amazonaws.com/webchat.js"
        )

        result = self.usecase.execute(self.dto)

        self.assertIsInstance(result, PublishWebchatResult)
        self.assertEqual(
            result.script_url, "https://bucket.s3.amazonaws.com/webchat.js"
        )
        self.integrations_service.get_channel_app.assert_called_once_with(
            apptype="wwc", app_uuid=self.dto.app_uuid
        )
        self.webchat_push_service.publish_webchat_script.assert_called_once_with(
            script_url="https://example.com/wwc.js",
            account_id=self.dto.account_id,
        )

    def test_execute_raises_validation_error_when_app_not_found(self):
        self.integrations_service.get_channel_app.return_value = None

        with self.assertRaises(ValidationError):
            self.usecase.execute(self.dto)

        self.webchat_push_service.publish_webchat_script.assert_not_called()

    def test_execute_raises_validation_error_when_script_missing(self):
        self.integrations_service.get_channel_app.return_value = {"config": {}}

        with self.assertRaises(ValidationError):
            self.usecase.execute(self.dto)

        self.webchat_push_service.publish_webchat_script.assert_not_called()

    def test_execute_raises_validation_error_when_config_missing(self):
        self.integrations_service.get_channel_app.return_value = {}

        with self.assertRaises(ValidationError):
            self.usecase.execute(self.dto)

    def test_execute_raises_api_exception_on_publish_failure(self):
        self.integrations_service.get_channel_app.return_value = {
            "config": {"script": "https://example.com/wwc.js"}
        }
        self.webchat_push_service.publish_webchat_script.side_effect = (
            WebchatPublishError("S3 error")
        )

        with self.assertRaises(APIException):
            self.usecase.execute(self.dto)

    def test_result_to_dict(self):
        result = PublishWebchatResult(script_url="https://example.com/webchat.js")

        self.assertEqual(
            result.to_dict(), {"script_url": "https://example.com/webchat.js"}
        )
