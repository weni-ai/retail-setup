from io import BytesIO
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from django.test import SimpleTestCase, override_settings

from retail.clients.aws_s3.client import S3Client


class TestS3ClientInit(SimpleTestCase):
    @patch("retail.clients.aws_s3.client.boto3")
    def test_bucket_name_arg_wins_over_settings(self, mock_boto3):
        with override_settings(AWS_STORAGE_BUCKET_NAME="settings-bucket"):
            client = S3Client(bucket_name="arg-bucket")

        self.assertEqual(client.bucket_name, "arg-bucket")

    @patch("retail.clients.aws_s3.client.boto3")
    def test_falls_back_to_settings_bucket_name(self, mock_boto3):
        with override_settings(AWS_STORAGE_BUCKET_NAME="settings-bucket"):
            client = S3Client()

        self.assertEqual(client.bucket_name, "settings-bucket")

    @patch("retail.clients.aws_s3.client.boto3")
    def test_falls_back_to_test_bucket_when_setting_missing(self, mock_boto3):
        # The production code uses ``getattr(settings, "AWS_STORAGE_BUCKET_NAME",
        # "test-bucket")``, so we simulate a settings object where the attribute
        # is simply absent and expect the hard-coded fallback to take over.
        fake_settings = MagicMock(spec=[])
        with patch("retail.clients.aws_s3.client.settings", fake_settings):
            client = S3Client()

        self.assertEqual(client.bucket_name, "test-bucket")

    @patch("retail.clients.aws_s3.client.boto3")
    def test_constructor_builds_boto_s3_client(self, mock_boto3):
        S3Client(bucket_name="any")

        mock_boto3.client.assert_called_once_with("s3")


class _S3ClientBotoMixin:
    """Shared setUp that isolates the ``boto3.client('s3')`` dependency."""

    def setUp(self):
        super().setUp()
        self.boto_patcher = patch("retail.clients.aws_s3.client.boto3")
        self.mock_boto3 = self.boto_patcher.start()
        self.mock_s3 = MagicMock()
        self.mock_boto3.client.return_value = self.mock_s3
        self.addCleanup(self.boto_patcher.stop)

        self.client = S3Client(bucket_name="my-bucket")


class TestS3ClientGetObject(_S3ClientBotoMixin, SimpleTestCase):
    def test_get_object_returns_body_bytes(self):
        body = MagicMock()
        body.read.return_value = b"file-content"
        self.mock_s3.get_object.return_value = {"Body": body}

        result = self.client.get_object("traces/execution.json")

        self.mock_s3.get_object.assert_called_once_with(
            Bucket="my-bucket", Key="traces/execution.json"
        )
        body.read.assert_called_once_with()
        self.assertEqual(result, b"file-content")

    def test_get_object_no_such_key_returns_none_and_logs_warning(self):
        self.mock_s3.get_object.side_effect = ClientError(
            error_response={
                "Error": {"Code": "NoSuchKey", "Message": "The key does not exist"}
            },
            operation_name="GetObject",
        )

        with self.assertLogs("retail.clients.aws_s3.client", level="WARNING") as logs:
            result = self.client.get_object("traces/missing.json")

        self.assertIsNone(result)
        self.assertTrue(
            any("traces/missing.json" in message for message in logs.output),
            logs.output,
        )

    def test_get_object_other_client_error_logs_and_reraises(self):
        self.mock_s3.get_object.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "nope"}},
            operation_name="GetObject",
        )

        with self.assertLogs("retail.clients.aws_s3.client", level="ERROR") as logs:
            with self.assertRaises(ClientError):
                self.client.get_object("traces/forbidden.json")

        self.assertTrue(
            any("traces/forbidden.json" in message for message in logs.output),
            logs.output,
        )

    def test_get_object_missing_error_code_is_treated_as_non_not_found(self):
        # Defensive: ClientError with no ``Error.Code`` still re-raises rather
        # than being silently swallowed.
        self.mock_s3.get_object.side_effect = ClientError(
            error_response={}, operation_name="GetObject"
        )

        with self.assertLogs("retail.clients.aws_s3.client", level="ERROR"):
            with self.assertRaises(ClientError):
                self.client.get_object("traces/weird.json")


class TestS3ClientPutObject(_S3ClientBotoMixin, SimpleTestCase):
    def test_put_object_forwards_all_fields_and_returns_key(self):
        result = self.client.put_object("traces/out.json", b'{"ok": true}')

        self.mock_s3.put_object.assert_called_once_with(
            Bucket="my-bucket",
            Key="traces/out.json",
            Body=b'{"ok": true}',
            ContentType="application/json",
        )
        self.assertEqual(result, "traces/out.json")

    def test_put_object_uses_custom_content_type(self):
        self.client.put_object("uploads/note.txt", b"hello", content_type="text/plain")

        _, kwargs = self.mock_s3.put_object.call_args
        self.assertEqual(kwargs["ContentType"], "text/plain")
        self.assertEqual(kwargs["Body"], b"hello")

    def test_put_object_propagates_boto_error(self):
        self.mock_s3.put_object.side_effect = ClientError(
            error_response={"Error": {"Code": "InternalError"}},
            operation_name="PutObject",
        )

        with self.assertRaises(ClientError):
            self.client.put_object("traces/fail.json", b"{}")


class TestS3ClientUploadFileobj(_S3ClientBotoMixin, SimpleTestCase):
    def test_upload_fileobj_forwards_stream_and_returns_key(self):
        fileobj = BytesIO(b"col\nval\n")

        result = self.client.upload_fileobj(fileobj, "exports/out.csv")

        self.mock_s3.upload_fileobj.assert_called_once_with(
            fileobj,
            "my-bucket",
            "exports/out.csv",
            ExtraArgs={"ContentType": "application/octet-stream"},
        )
        self.assertEqual(result, "exports/out.csv")

    def test_upload_fileobj_uses_custom_content_type(self):
        fileobj = BytesIO(b"col\nval\n")

        self.client.upload_fileobj(fileobj, "exports/out.csv", content_type="text/csv")

        _, kwargs = self.mock_s3.upload_fileobj.call_args
        self.assertEqual(kwargs["ExtraArgs"], {"ContentType": "text/csv"})

    def test_upload_fileobj_propagates_boto_error(self):
        self.mock_s3.upload_fileobj.side_effect = ClientError(
            error_response={"Error": {"Code": "InternalError"}},
            operation_name="PutObject",
        )

        with self.assertRaises(ClientError):
            self.client.upload_fileobj(BytesIO(b"x"), "exports/fail.csv")
