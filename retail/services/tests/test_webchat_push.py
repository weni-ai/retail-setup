from unittest.mock import MagicMock

from django.test import TestCase, override_settings

from retail.services.webchat_push.service import WebchatPublishError, WebchatPushService


@override_settings(WEBCHAT_CDN_URL="https://cdn.example.com/webchat.js")
class TestWebchatPushService(TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.service = WebchatPushService(client=self.mock_client)
        self.script_url = "https://integrations.example.com/wwc/script.js"
        self.account_id = "b1165658e9e54790881952eb99341e51"
        self.vtex_account = "mystore"

    def test_publish_webchat_script_success(self):
        self.mock_client.upload_script.side_effect = [
            f"https://bucket.s3.amazonaws.com/VTEXApp/accounts/{self.account_id}/webchat.js",
            f"https://bucket.s3.amazonaws.com/VTEXApp/accounts/{self.vtex_account}/webchat.js",
        ]

        result = self.service.publish_webchat_script(
            script_url=self.script_url,
            account_id=self.account_id,
            vtex_account=self.vtex_account,
        )

        self.assertEqual(result, [
            f"https://bucket.s3.amazonaws.com/VTEXApp/accounts/{self.account_id}/webchat.js",
            f"https://bucket.s3.amazonaws.com/VTEXApp/accounts/{self.vtex_account}/webchat.js",
        ])
        self.assertEqual(self.mock_client.upload_script.call_count, 2)

    def test_publish_webchat_script_builds_correct_keys(self):
        self.mock_client.upload_script.return_value = "https://example.com/script.js"

        self.service.publish_webchat_script(
            script_url=self.script_url,
            account_id=self.account_id,
            vtex_account=self.vtex_account,
        )

        calls = self.mock_client.upload_script.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            calls[0][1]["key"],
            f"VTEXApp/accounts/{self.account_id}/webchat.js",
        )
        self.assertEqual(
            calls[1][1]["key"],
            f"VTEXApp/accounts/{self.vtex_account}/webchat.js",
        )

    def test_publish_webchat_script_upload_failure_raises_webchat_publish_error(self):
        self.mock_client.upload_script.side_effect = Exception("S3 connection failed")

        with self.assertRaises(WebchatPublishError) as ctx:
            self.service.publish_webchat_script(
                script_url=self.script_url,
                account_id=self.account_id,
                vtex_account=self.vtex_account,
            )

        self.assertIn("S3 connection failed", str(ctx.exception))

    def test_build_loader_script_replaces_placeholders(self):
        script = self.service._build_loader_script(self.script_url)

        self.assertIn("https://cdn.example.com/webchat.js", script)
        self.assertIn(self.script_url, script)
        self.assertNotIn("<CDN_URL>", script)
        self.assertNotIn("<SCRIPT_URL>", script)
