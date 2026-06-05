from unittest.mock import Mock, patch

from django.test import TestCase
from django.core.files.uploadedfile import InMemoryUploadedFile

from io import BytesIO

from retail.services.aws_s3.service import S3Service
from retail.services.aws_s3.converters import Base64ToUploadedFileConverter
from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.interfaces.clients.aws_s3.client import S3ClientInterface


class TestS3Service(TestCase):
    def setUp(self):
        self.mock_client = Mock(spec=S3ClientInterface)
        self.service = S3Service(client=self.mock_client)
        self.test_key = "test/file.jpg"
        self.test_file = self._create_test_file()

    def _create_test_file(self):
        file_content = b"test file content"
        file_io = BytesIO(file_content)
        return InMemoryUploadedFile(
            file=file_io,
            field_name="test_field",
            name="test.jpg",
            content_type="image/jpeg",
            size=len(file_content),
            charset=None,
        )

    def test_service_implements_interface(self):
        self.assertIsInstance(self.service, S3ServiceInterface)

    def test_init_with_client(self):
        service = S3Service(client=self.mock_client)
        self.assertEqual(service.client, self.mock_client)
        self.assertIsInstance(service.base_64_converter, Base64ToUploadedFileConverter)

    @patch("retail.services.aws_s3.service.S3Client")
    def test_init_without_client(self, mock_s3_client):
        S3Service()
        mock_s3_client.assert_called_once()

    @patch("retail.services.aws_s3.service.S3Client")
    def test_init_forwards_bucket_name_to_client(self, mock_s3_client):
        """Allowing the service to be bound to a specific bucket lets
        callers (e.g. the agent execution traces storage) reuse the
        service layer instead of instantiating ``S3Client`` directly.
        """
        S3Service(bucket_name="custom-bucket")
        mock_s3_client.assert_called_once_with(bucket_name="custom-bucket")

    def test_upload_file_success(self):
        expected_key = "uploaded/file.jpg"
        self.mock_client.upload_file.return_value = expected_key

        result = self.service.upload_file(self.test_file, self.test_key)

        self.mock_client.upload_file.assert_called_once_with(
            self.test_file, self.test_key
        )
        self.assertEqual(result, expected_key)

    def test_upload_file_with_different_key(self):
        custom_key = "custom/path/image.png"
        expected_key = "s3://bucket/custom/path/image.png"
        self.mock_client.upload_file.return_value = expected_key

        result = self.service.upload_file(self.test_file, custom_key)

        self.mock_client.upload_file.assert_called_once_with(self.test_file, custom_key)
        self.assertEqual(result, expected_key)

    def test_upload_file_client_error(self):
        self.mock_client.upload_file.side_effect = Exception("S3 upload failed")

        with self.assertRaises(Exception) as context:
            self.service.upload_file(self.test_file, self.test_key)

        self.assertIn("S3 upload failed", str(context.exception))
        self.mock_client.upload_file.assert_called_once_with(
            self.test_file, self.test_key
        )

    def test_generate_presigned_url_default_expiration(self):
        expected_url = "https://s3.amazonaws.com/bucket/test/file.jpg?signature=abc123"
        self.mock_client.generate_presigned_url.return_value = expected_url

        result = self.service.generate_presigned_url(self.test_key)

        self.mock_client.generate_presigned_url.assert_called_once_with(
            self.test_key, 3600
        )
        self.assertEqual(result, expected_url)

    def test_generate_presigned_url_custom_expiration(self):
        custom_expiration = 7200
        expected_url = "https://s3.amazonaws.com/bucket/test/file.jpg?signature=def456"
        self.mock_client.generate_presigned_url.return_value = expected_url

        result = self.service.generate_presigned_url(self.test_key, custom_expiration)

        self.mock_client.generate_presigned_url.assert_called_once_with(
            self.test_key, custom_expiration
        )
        self.assertEqual(result, expected_url)

    def test_generate_presigned_url_with_special_characters(self):
        special_key = "folder/file with spaces & symbols.jpg"
        expected_url = "https://s3.amazonaws.com/bucket/folder/file%20with%20spaces%20%26%20symbols.jpg"
        self.mock_client.generate_presigned_url.return_value = expected_url

        result = self.service.generate_presigned_url(special_key)

        self.mock_client.generate_presigned_url.assert_called_once_with(
            special_key, 3600
        )
        self.assertEqual(result, expected_url)

    def test_generate_presigned_url_client_error(self):
        self.mock_client.generate_presigned_url.side_effect = Exception(
            "URL generation failed"
        )

        with self.assertRaises(Exception) as context:
            self.service.generate_presigned_url(self.test_key)

        self.assertIn("URL generation failed", str(context.exception))
        self.mock_client.generate_presigned_url.assert_called_once_with(
            self.test_key, 3600
        )

    def test_base_64_converter_is_available(self):
        self.assertIsInstance(
            self.service.base_64_converter, Base64ToUploadedFileConverter
        )

    def test_base_64_converter_can_be_used(self):
        import base64

        test_data = b"test converter integration"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:image/png;base64,{base64_data}"

        converted_file = self.service.base_64_converter.convert(data_uri)

        self.assertIsInstance(converted_file, InMemoryUploadedFile)
        self.assertEqual(converted_file.content_type, "image/png")
        self.assertTrue(converted_file.name.endswith(".png"))

    def test_upload_converted_base64_file(self):
        import base64

        test_data = b"test upload base64"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{base64_data}"

        converted_file = self.service.base_64_converter.convert(data_uri)

        expected_key = "uploads/converted_file.jpeg"
        self.mock_client.upload_file.return_value = expected_key

        result = self.service.upload_file(converted_file, "uploads/converted_file.jpeg")

        self.assertEqual(result, expected_key)
        self.mock_client.upload_file.assert_called_once()

    def test_service_methods_preserve_interfaces(self):
        import inspect

        upload_signature = inspect.signature(self.service.upload_file)
        self.assertEqual(len(upload_signature.parameters), 2)
        self.assertIn("file", upload_signature.parameters)
        self.assertIn("key", upload_signature.parameters)

        presigned_signature = inspect.signature(self.service.generate_presigned_url)
        self.assertEqual(len(presigned_signature.parameters), 2)
        self.assertIn("key", presigned_signature.parameters)
        self.assertIn("expiration", presigned_signature.parameters)

    def test_upload_file_with_empty_file(self):
        empty_file = InMemoryUploadedFile(
            file=BytesIO(b""),
            field_name="empty",
            name="empty.txt",
            content_type="text/plain",
            size=0,
            charset=None,
        )
        expected_key = "empty/file.txt"
        self.mock_client.upload_file.return_value = expected_key

        result = self.service.upload_file(empty_file, "empty/file.txt")

        self.assertEqual(result, expected_key)
        self.mock_client.upload_file.assert_called_once_with(
            empty_file, "empty/file.txt"
        )

    def test_generate_presigned_url_zero_expiration(self):
        expected_url = "https://s3.amazonaws.com/bucket/test.jpg"
        self.mock_client.generate_presigned_url.return_value = expected_url

        result = self.service.generate_presigned_url(self.test_key, 0)

        self.mock_client.generate_presigned_url.assert_called_once_with(
            self.test_key, 0
        )
        self.assertEqual(result, expected_url)

    def test_generate_presigned_url_negative_expiration(self):
        expected_url = "https://s3.amazonaws.com/bucket/test.jpg"
        self.mock_client.generate_presigned_url.return_value = expected_url

        result = self.service.generate_presigned_url(self.test_key, -1)

        self.mock_client.generate_presigned_url.assert_called_once_with(
            self.test_key, -1
        )
        self.assertEqual(result, expected_url)

    def test_client_is_accessible(self):
        self.assertEqual(self.service.client, self.mock_client)

    def test_service_handles_large_files(self):
        large_content = b"x" * (10 * 1024 * 1024)
        large_file = InMemoryUploadedFile(
            file=BytesIO(large_content),
            field_name="large",
            name="large_file.bin",
            content_type="application/octet-stream",
            size=len(large_content),
            charset=None,
        )

        expected_key = "large/file.bin"
        self.mock_client.upload_file.return_value = expected_key

        result = self.service.upload_file(large_file, "large/file.bin")

        self.assertEqual(result, expected_key)
        self.mock_client.upload_file.assert_called_once_with(
            large_file, "large/file.bin"
        )

    def test_get_object_passes_key_and_returns_client_bytes(self):
        """The service is a thin pass-through to the injected client and must
        not alter the bytes returned by S3 (used by the traces download flow).
        """
        self.mock_client.get_object.return_value = b'{"trace": true}'

        result = self.service.get_object(self.test_key)

        self.mock_client.get_object.assert_called_once_with(self.test_key)
        self.assertEqual(result, b'{"trace": true}')

    def test_get_object_returns_none_when_client_returns_none(self):
        """When the underlying object is missing the client surfaces ``None``
        and the service must propagate it unchanged so callers can branch on
        it (e.g. show an empty trace view).
        """
        self.mock_client.get_object.return_value = None

        result = self.service.get_object("missing/key.json")

        self.mock_client.get_object.assert_called_once_with("missing/key.json")
        self.assertIsNone(result)

    def test_get_object_propagates_client_error(self):
        self.mock_client.get_object.side_effect = Exception("boom")

        with self.assertRaises(Exception) as context:
            self.service.get_object(self.test_key)

        self.assertIn("boom", str(context.exception))
        self.mock_client.get_object.assert_called_once_with(self.test_key)

    def test_put_object_default_content_type(self):
        expected_key = "traces/out.json"
        self.mock_client.put_object.return_value = expected_key

        result = self.service.put_object(expected_key, b"{}")

        self.mock_client.put_object.assert_called_once_with(
            expected_key, b"{}", "application/json"
        )
        self.assertEqual(result, expected_key)

    def test_put_object_custom_content_type(self):
        expected_key = "logs/line.txt"
        self.mock_client.put_object.return_value = expected_key

        result = self.service.put_object(
            expected_key, b"hello", content_type="text/plain"
        )

        self.mock_client.put_object.assert_called_once_with(
            expected_key, b"hello", "text/plain"
        )
        self.assertEqual(result, expected_key)

    def test_put_object_propagates_client_error(self):
        self.mock_client.put_object.side_effect = Exception("put failed")

        with self.assertRaises(Exception) as context:
            self.service.put_object("bad/key.json", b"{}")

        self.assertIn("put failed", str(context.exception))
        self.mock_client.put_object.assert_called_once_with(
            "bad/key.json", b"{}", "application/json"
        )

    def test_upload_fileobj_default_content_type(self):
        expected_key = "exports/out.csv"
        self.mock_client.upload_fileobj.return_value = expected_key
        fileobj = BytesIO(b"col\nval\n")

        result = self.service.upload_fileobj(fileobj, expected_key)

        self.mock_client.upload_fileobj.assert_called_once_with(
            fileobj, expected_key, "application/octet-stream"
        )
        self.assertEqual(result, expected_key)

    def test_upload_fileobj_custom_content_type(self):
        expected_key = "exports/out.csv"
        self.mock_client.upload_fileobj.return_value = expected_key
        fileobj = BytesIO(b"col\nval\n")

        result = self.service.upload_fileobj(
            fileobj, expected_key, content_type="text/csv"
        )

        self.mock_client.upload_fileobj.assert_called_once_with(
            fileobj, expected_key, "text/csv"
        )
        self.assertEqual(result, expected_key)

    def test_upload_fileobj_propagates_client_error(self):
        self.mock_client.upload_fileobj.side_effect = Exception("stream failed")

        with self.assertRaises(Exception) as context:
            self.service.upload_fileobj(BytesIO(b"x"), "bad/key.csv")

        self.assertIn("stream failed", str(context.exception))
