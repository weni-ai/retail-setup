import base64
from unittest.mock import patch, Mock

from django.test import TestCase
from django.core.files.uploadedfile import InMemoryUploadedFile

from retail.services.aws_s3.converters import (
    Base64ToUploadedFileConverter,
    ConverterInterface,
    ImageUrlToBase64Converter,
)


class TestBase64ToUploadedFileConverter(TestCase):
    def setUp(self):
        self.converter = Base64ToUploadedFileConverter()

    def test_converter_has_convert_method(self):
        self.assertTrue(hasattr(self.converter, "convert"))
        self.assertTrue(callable(self.converter.convert))

    def test_convert_with_complete_data_uri(self):
        test_data = b"test image data"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:image/png;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.content_type, "image/png")
        self.assertTrue(result.name.endswith(".png"))
        self.assertEqual(result.size, len(test_data))
        self.assertEqual(result.read(), test_data)

    def test_convert_with_jpeg_content_type(self):
        test_data = b"jpeg image data"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.content_type, "image/jpeg")
        self.assertTrue(result.name.endswith(".jpeg"))
        self.assertEqual(result.size, len(test_data))

    def test_convert_without_header(self):
        test_data = b"raw base64 data"
        base64_data = base64.b64encode(test_data).decode("utf-8")

        result = self.converter.convert(base64_data)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.content_type, "image/jpeg")
        self.assertTrue(result.name.endswith(".jpg"))
        self.assertEqual(result.size, len(test_data))
        self.assertEqual(result.read(), test_data)

    def test_convert_with_invalid_header_format(self):
        test_data = b"data with bad header"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"invalid-header,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.content_type, "image/jpeg")
        self.assertTrue(result.name.endswith(".jpg"))

    def test_convert_with_data_without_semicolon_valid_base64(self):
        test_data = b"test data"
        base64_data = base64.b64encode(test_data).decode("utf-8")

        result = self.converter.convert(base64_data)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.content_type, "image/jpeg")
        self.assertTrue(result.name.endswith(".jpg"))
        self.assertEqual(result.size, len(test_data))

    def test_convert_with_empty_content_type(self):
        test_data = b"test data"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.content_type, "image/jpeg")
        self.assertTrue(result.name.endswith(".jpg"))
        self.assertEqual(result.size, len(test_data))

    def test_convert_with_content_type_without_slash(self):
        test_data = b"test data"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:plaintext;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.content_type, "image/jpeg")
        self.assertTrue(result.name.endswith(".jpg"))
        self.assertEqual(result.size, len(test_data))

    @patch("retail.services.aws_s3.converters.uuid4")
    def test_convert_generates_unique_filename(self, mock_uuid4):
        mock_uuid4.return_value.hex = "abcdef123456"
        test_data = b"test data"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:image/png;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertEqual(result.name, "abcdef123456.png")
        mock_uuid4.assert_called_once()

    def test_convert_with_large_file(self):
        test_data = b"x" * (1024 * 1024)
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:application/octet-stream;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.size, len(test_data))

    def test_convert_with_empty_base64_data(self):
        data_uri = "data:text/plain;base64,"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.size, 0)
        self.assertEqual(result.read(), b"")

    def test_convert_file_position_reset(self):
        test_data = b"test position reset"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:text/plain;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        first_read = result.read()
        self.assertEqual(first_read, test_data)

        result.seek(0)
        second_read = result.read()
        self.assertEqual(second_read, test_data)

    def test_convert_with_multiple_commas_in_data(self):
        test_data = b"data,with,commas"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:text/csv;base64,{base64_data},extra,data"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)

    def test_converter_interface_protocol(self):
        self.assertTrue(hasattr(ConverterInterface, "convert"))

    def test_converter_implements_protocol_duck_typing(self):
        self.assertTrue(hasattr(self.converter, "convert"))
        self.assertTrue(callable(getattr(self.converter, "convert")))

    def test_file_io_buffer_properties(self):
        test_data = b"buffer test"
        base64_data = base64.b64encode(test_data).decode("utf-8")

        result = self.converter.convert(base64_data)

        result.seek(0)
        self.assertEqual(result.tell(), 0)
        result.seek(0, 2)
        self.assertEqual(result.tell(), len(test_data))


class TestImageUrlToBase64Converter(TestCase):
    def setUp(self):
        self.converter = ImageUrlToBase64Converter()

    # Tests for is_image_url method
    def test_is_image_url_with_png(self):
        url = "https://example.com/image.png"
        self.assertTrue(self.converter.is_image_url(url))

    def test_is_image_url_with_jpg(self):
        url = "https://example.com/photo.jpg"
        self.assertTrue(self.converter.is_image_url(url))

    def test_is_image_url_with_jpeg(self):
        url = "https://example.com/photo.jpeg"
        self.assertTrue(self.converter.is_image_url(url))

    def test_is_image_url_with_s3_presigned_url(self):
        """S3 presigned URLs with query string should be detected."""
        url = (
            "https://bucket.s3.amazonaws.com/image.png?AWSAccessKeyId=xxx&Signature=yyy"
        )
        self.assertTrue(self.converter.is_image_url(url))

    def test_is_image_url_with_non_image(self):
        url = "https://example.com/page.html"
        self.assertFalse(self.converter.is_image_url(url))

    def test_is_image_url_with_non_url(self):
        text = "just some text"
        self.assertFalse(self.converter.is_image_url(text))

    def test_is_image_url_with_none(self):
        self.assertFalse(self.converter.is_image_url(None))

    def test_is_image_url_with_empty_string(self):
        self.assertFalse(self.converter.is_image_url(""))

    def test_is_image_url_case_insensitive(self):
        url = "https://example.com/image.PNG"
        self.assertTrue(self.converter.is_image_url(url))

    # Tests for convert method
    @patch("retail.services.aws_s3.converters.requests.get")
    def test_convert_success(self, mock_get):
        """Successful conversion returns base64 Data URI."""
        mock_response = Mock()
        mock_response.content = b"fake image content"
        mock_response.headers = {"Content-Type": "image/png"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        url = "https://example.com/image.png"
        result = self.converter.convert(url)

        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("data:image/png;base64,"))
        # Verify the base64 content is correct
        expected_base64 = base64.b64encode(b"fake image content").decode("utf-8")
        self.assertIn(expected_base64, result)

    @patch("retail.services.aws_s3.converters.requests.get")
    def test_convert_with_content_type_charset(self, mock_get):
        """Content-Type with charset should be cleaned."""
        mock_response = Mock()
        mock_response.content = b"image data"
        mock_response.headers = {"Content-Type": "image/jpeg; charset=utf-8"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        url = "https://example.com/image.jpg"
        result = self.converter.convert(url)

        self.assertTrue(result.startswith("data:image/jpeg;base64,"))

    @patch("retail.services.aws_s3.converters.requests.get")
    def test_convert_with_missing_content_type(self, mock_get):
        """Missing Content-Type should use default."""
        mock_response = Mock()
        mock_response.content = b"image data"
        mock_response.headers = {}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        url = "https://example.com/image.png"
        result = self.converter.convert(url)

        self.assertTrue(result.startswith("data:image/png;base64,"))

    def test_convert_with_non_image_url(self):
        """Non-image URL should return None."""
        url = "https://example.com/page.html"
        result = self.converter.convert(url)
        self.assertIsNone(result)

    @patch("retail.services.aws_s3.converters.requests.get")
    def test_convert_request_failure(self, mock_get):
        """Request failure should return None."""
        import requests

        mock_get.side_effect = requests.RequestException("Connection error")

        url = "https://example.com/image.png"
        result = self.converter.convert(url)

        self.assertIsNone(result)

    @patch("retail.services.aws_s3.converters.requests.get")
    def test_convert_http_error(self, mock_get):
        """HTTP error should return None."""
        import requests

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        url = "https://example.com/image.png"
        result = self.converter.convert(url)

        self.assertIsNone(result)

    @patch("retail.services.aws_s3.converters.requests.get")
    def test_convert_uses_timeout(self, mock_get):
        """Request should use timeout."""
        mock_response = Mock()
        mock_response.content = b"image data"
        mock_response.headers = {"Content-Type": "image/png"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        url = "https://example.com/image.png"
        self.converter.convert(url)

        mock_get.assert_called_once_with(url, timeout=30)
