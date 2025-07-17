import base64

from unittest.mock import patch

from django.test import TestCase
from django.core.files.uploadedfile import InMemoryUploadedFile

from retail.services.aws_s3.converters import (
    Base64ToUploadedFileConverter,
    ConverterInterface,
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

    def test_convert_with_pdf_content_type(self):
        test_data = b"pdf document data"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:application/pdf;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.content_type, "application/pdf")
        self.assertTrue(result.name.endswith(".pdf"))
        self.assertEqual(result.size, len(test_data))

    def test_convert_without_header(self):
        test_data = b"raw base64 data"
        base64_data = base64.b64encode(test_data).decode("utf-8")

        result = self.converter.convert(base64_data)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertIsNone(result.content_type)
        self.assertNotIn(".", result.name)
        self.assertEqual(result.size, len(test_data))
        self.assertEqual(result.read(), test_data)

    def test_convert_with_invalid_header_format(self):
        test_data = b"data with bad header"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"invalid-header,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertIsNone(result.content_type)
        self.assertNotIn(".", result.name)
        self.assertEqual(result.size, len(test_data))

    def test_convert_with_data_without_semicolon_valid_base64(self):
        test_data = b"test data"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = base64_data

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertIsNone(result.content_type)
        self.assertNotIn(".", result.name)
        self.assertEqual(result.size, len(test_data))

    def test_convert_with_empty_content_type(self):
        test_data = b"test data"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.content_type, "")
        self.assertNotIn(".", result.name)
        self.assertEqual(result.size, len(test_data))

    def test_convert_with_content_type_without_slash(self):
        test_data = b"test data"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:plaintext;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.content_type, "plaintext")
        self.assertNotIn(".", result.name)
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

    def test_convert_file_has_correct_properties(self):
        test_data = b"test file properties"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:text/plain;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertIsNone(result.field_name)
        self.assertEqual(result.content_type, "text/plain")
        self.assertEqual(result.size, len(test_data))
        self.assertIsNone(result.charset)
        self.assertTrue(result.name.endswith(".plain"))

    def test_convert_with_large_file(self):
        test_data = b"x" * (1024 * 1024)
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:application/octet-stream;base64,{base64_data}"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.size, len(test_data))
        self.assertEqual(result.content_type, "application/octet-stream")

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
        self.assertEqual(first_read, second_read)

    def test_convert_with_multiple_commas_in_data(self):
        test_data = b"data,with,commas"
        base64_data = base64.b64encode(test_data).decode("utf-8")
        data_uri = f"data:text/csv;base64,{base64_data},extra,data"

        result = self.converter.convert(data_uri)

        self.assertIsInstance(result, InMemoryUploadedFile)
        self.assertEqual(result.content_type, "text/csv")

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
