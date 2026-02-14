from unittest.mock import Mock, patch

from django.test import TestCase
from django.core.files.uploadedfile import InMemoryUploadedFile

from retail.templates.handlers.template_metadata import TemplateMetadataHandler
from retail.interfaces.services.aws_s3 import S3ServiceInterface


class TestTemplateMetadataHandler(TestCase):
    def setUp(self):
        self.mock_s3_service = Mock(spec=S3ServiceInterface)
        self.mock_converter = Mock()
        self.mock_s3_service.base_64_converter = self.mock_converter
        self.handler = TemplateMetadataHandler(s3_service=self.mock_s3_service)

    def test_init_with_s3_service(self):
        handler = TemplateMetadataHandler(s3_service=self.mock_s3_service)
        self.assertEqual(handler.s3_service, self.mock_s3_service)

    @patch("retail.templates.handlers.template_metadata.S3Service")
    def test_init_without_s3_service(self, mock_s3_service_class):
        TemplateMetadataHandler()
        mock_s3_service_class.assert_called_once()

    def test_upload_header_image_success(self):
        mock_file = Mock(spec=InMemoryUploadedFile)
        mock_file.name = "image.jpg"
        self.mock_converter.convert.return_value = mock_file

        expected_key = "template_headers/12345678.jpg"
        self.mock_s3_service.upload_file.return_value = expected_key

        header = {"text": "base64_image_data"}

        with patch(
            "retail.templates.handlers.template_metadata.uuid.uuid4"
        ) as mock_uuid:
            mock_uuid.return_value = "12345678"
            result = self.handler._upload_header_image(header)

        self.mock_converter.convert.assert_called_once_with("base64_image_data")
        self.mock_s3_service.upload_file.assert_called_once_with(
            mock_file, "template_headers/12345678.jpg"
        )
        self.assertEqual(result, expected_key)

    def test_upload_header_image_with_extension(self):
        mock_file = Mock(spec=InMemoryUploadedFile)
        mock_file.name = "image.png"
        self.mock_converter.convert.return_value = mock_file

        expected_key = "template_headers/abcdef.png"
        self.mock_s3_service.upload_file.return_value = expected_key

        header = {"text": "base64_png_data"}

        with patch(
            "retail.templates.handlers.template_metadata.uuid.uuid4"
        ) as mock_uuid:
            mock_uuid.return_value = "abcdef"
            result = self.handler._upload_header_image(header)

        self.mock_s3_service.upload_file.assert_called_once_with(
            mock_file, "template_headers/abcdef.png"
        )
        self.assertEqual(result, expected_key)

    def test_upload_header_image_without_extension(self):
        mock_file = Mock(spec=InMemoryUploadedFile)
        mock_file.name = "imagefile"
        self.mock_converter.convert.return_value = mock_file

        expected_key = "template_headers/noext123.jpg"
        self.mock_s3_service.upload_file.return_value = expected_key

        header = {"text": "base64_data"}

        with patch(
            "retail.templates.handlers.template_metadata.uuid.uuid4"
        ) as mock_uuid:
            mock_uuid.return_value = "noext123"
            result = self.handler._upload_header_image(header)

        self.mock_s3_service.upload_file.assert_called_once_with(
            mock_file, "template_headers/noext123.jpg"
        )
        self.assertEqual(result, expected_key)

    def test_build_metadata_complete(self):
        translation = {
            "template_body": "Hello {{name}}",
            "template_body_params": ["name"],
            "template_header": {"type": "TEXT", "text": "Header"},
            "template_footer": "Footer text",
            "template_button": [{"type": "QUICK_REPLY", "text": "Reply"}],
            "category": "MARKETING",
            "language": "es_MX",
        }
        category = "UTILITY"

        result = self.handler.build_metadata(translation, category)

        expected = {
            "body": "Hello {{name}}",
            "body_params": ["name"],
            "header": {"type": "TEXT", "text": "Header"},
            "footer": "Footer text",
            "buttons": [{"type": "QUICK_REPLY", "text": "Reply"}],
            "category": "UTILITY",
            "language": "es_MX",
        }
        self.assertEqual(result, expected)

    def test_build_metadata_partial(self):
        translation = {
            "template_body": "Simple message",
            "template_footer": "Simple footer",
        }

        result = self.handler.build_metadata(translation)

        expected = {
            "body": "Simple message",
            "body_params": None,
            "header": None,
            "footer": "Simple footer",
            "buttons": None,
            "category": None,
            "language": None,
        }
        self.assertEqual(result, expected)

    def test_build_metadata_with_category_from_translation(self):
        translation = {"template_body": "Test message", "category": "AUTHENTICATION"}

        result = self.handler.build_metadata(translation)

        self.assertEqual(result["category"], "AUTHENTICATION")

    def test_build_metadata_empty_translation(self):
        translation = {}

        result = self.handler.build_metadata(translation)

        expected = {
            "body": None,
            "body_params": None,
            "header": None,
            "footer": None,
            "buttons": None,
            "category": None,
            "language": None,
        }
        self.assertEqual(result, expected)

    def test_post_process_translation_with_buttons(self):
        metadata = {"body": "Original", "buttons": "old_buttons"}
        translation_payload = {"buttons": [{"type": "URL", "text": "New Button"}]}

        result = self.handler.post_process_translation(metadata, translation_payload)

        self.assertEqual(result["buttons"], [{"type": "URL", "text": "New Button"}])
        self.assertEqual(result["body"], "Original")

    def test_post_process_translation_with_header_upload(self):
        metadata = {"body": "Test"}
        translation_payload = {
            "header": {"header_type": "IMAGE", "text": "base64_image"}
        }

        expected_key = "template_headers/uploaded_image.jpg"
        with patch.object(
            self.handler, "_upload_header_image", return_value=expected_key
        ):
            result = self.handler.post_process_translation(
                metadata, translation_payload
            )

        self.assertEqual(
            result["header"], {"header_type": "IMAGE", "text": expected_key}
        )
        self.assertEqual(result["body"], "Test")

    def test_post_process_translation_with_both_buttons_and_header(self):
        metadata = {"body": "Test", "category": "UTILITY"}
        translation_payload = {
            "buttons": [{"type": "QUICK_REPLY", "text": "Quick"}],
            "header": {"header_type": "TEXT", "text": "Header Text"},
        }

        with patch.object(
            self.handler, "_upload_header_image", return_value="uploaded_header_key"
        ):
            result = self.handler.post_process_translation(
                metadata, translation_payload
            )

        self.assertEqual(result["buttons"], [{"type": "QUICK_REPLY", "text": "Quick"}])
        self.assertEqual(
            result["header"], {"header_type": "TEXT", "text": "Header Text"}
        )
        self.assertEqual(result["body"], "Test")
        self.assertEqual(result["category"], "UTILITY")

    def test_post_process_translation_with_s3_url_does_not_reupload(self):
        """When header text is already an S3 URL, should not re-upload."""
        s3_url = "https://weni-staging-retail.s3.amazonaws.com/template_headers/image.png?token=abc"
        metadata = {"body": "Test"}
        translation_payload = {"header": {"header_type": "IMAGE", "text": s3_url}}

        with patch.object(self.handler, "_upload_header_image") as mock_upload:
            result = self.handler.post_process_translation(
                metadata, translation_payload
            )

            # Should NOT call upload when it's already an S3 URL
            mock_upload.assert_not_called()

        # Should keep the original S3 URL
        self.assertEqual(result["header"]["text"], s3_url)
        self.assertEqual(result["header"]["header_type"], "IMAGE")

    def test_is_s3_url_with_https(self):
        self.assertTrue(self.handler._is_s3_url("https://example.com/image.png"))

    def test_is_s3_url_with_http(self):
        self.assertTrue(self.handler._is_s3_url("http://example.com/image.png"))

    def test_is_s3_url_with_base64(self):
        self.assertFalse(self.handler._is_s3_url("data:image/png;base64,iVBOR..."))

    def test_is_s3_url_with_none(self):
        self.assertFalse(self.handler._is_s3_url(None))

    def test_is_s3_url_with_empty_string(self):
        self.assertFalse(self.handler._is_s3_url(""))

    def test_post_process_translation_preserves_metadata(self):
        original_metadata = {"body": "Original", "footer": "Footer"}
        translation_payload = {}

        result = self.handler.post_process_translation(
            original_metadata, translation_payload
        )

        self.assertIsNot(result, original_metadata)
        self.assertEqual(result, original_metadata)

    def test_extract_start_condition_found(self):
        parameters = [
            {"name": "other_param", "value": "other_value"},
            {"name": "start_condition", "value": "user.is_active == true"},
            {"name": "another_param", "value": "another_value"},
        ]

        result = self.handler.extract_start_condition(parameters)

        self.assertEqual(result, "user.is_active == true")

    def test_extract_start_condition_not_found(self):
        parameters = [
            {"name": "other_param", "value": "other_value"},
            {"name": "different_param", "value": "different_value"},
        ]

        result = self.handler.extract_start_condition(parameters)

        self.assertIsNone(result)

    def test_extract_start_condition_with_default(self):
        parameters = [{"name": "other_param", "value": "other_value"}]
        default_value = "default_condition"

        result = self.handler.extract_start_condition(parameters, default_value)

        self.assertEqual(result, default_value)

    def test_extract_start_condition_empty_parameters(self):
        parameters = []

        result = self.handler.extract_start_condition(parameters)

        self.assertIsNone(result)

    def test_extract_variables_found(self):
        expected_variables = [
            {"name": "user_name", "type": "string"},
            {"name": "user_age", "type": "number"},
        ]
        parameters = [
            {"name": "start_condition", "value": "condition"},
            {"name": "variables", "value": expected_variables},
            {"name": "other_param", "value": "other"},
        ]

        result = self.handler.extract_variables(parameters)

        self.assertEqual(result, expected_variables)

    def test_extract_variables_not_found(self):
        parameters = [
            {"name": "start_condition", "value": "condition"},
            {"name": "other_param", "value": "other"},
        ]

        result = self.handler.extract_variables(parameters)

        self.assertIsNone(result)

    def test_extract_variables_with_default(self):
        parameters = [{"name": "other_param", "value": "other"}]
        default_variables = [{"name": "default_var", "type": "string"}]

        result = self.handler.extract_variables(parameters, default_variables)

        self.assertEqual(result, default_variables)

    def test_extract_variables_empty_parameters(self):
        parameters = []

        result = self.handler.extract_variables(parameters)

        self.assertIsNone(result)

    def test_extract_variables_empty_value(self):
        parameters = [{"name": "variables", "value": []}]

        result = self.handler.extract_variables(parameters)

        self.assertEqual(result, [])

    def test_multiple_parameters_with_same_name(self):
        parameters = [
            {"name": "start_condition", "value": "first_condition"},
            {"name": "start_condition", "value": "second_condition"},
            {"name": "other_param", "value": "other"},
        ]

        result = self.handler.extract_start_condition(parameters)

        self.assertEqual(result, "first_condition")


class TestConvertBodyToNumericForMeta(TestCase):
    """Tests for convert_body_to_numeric_for_meta method."""

    def setUp(self):
        self.mock_s3_service = Mock(spec=S3ServiceInterface)
        self.handler = TemplateMetadataHandler(s3_service=self.mock_s3_service)

    def test_converts_labeled_variables_to_numeric(self):
        """Should convert {{client_name}} to {{1}}, {{order_value}} to {{2}}."""
        translation_payload = {
            "body": {
                "type": "BODY",
                "text": "Olá {{client_name}}, seu pedido de {{order_value}} está pronto!",
            },
            "header": {"header_type": "TEXT", "text": "Pedido"},
        }

        result = self.handler.convert_body_to_numeric_for_meta(translation_payload)

        expected_body = "Olá {{1}}, seu pedido de {{2}} está pronto!"
        self.assertEqual(result["body"]["text"], expected_body)
        # Header should remain unchanged
        self.assertEqual(result["header"]["header_type"], "TEXT")
        self.assertEqual(result["header"]["text"], "Pedido")

    def test_preserves_already_numeric_variables(self):
        """Should not change body if variables are already numeric."""
        translation_payload = {
            "body": {
                "type": "BODY",
                "text": "Olá {{1}}, seu pedido {{2}} está pronto!",
            },
        }

        result = self.handler.convert_body_to_numeric_for_meta(translation_payload)

        self.assertEqual(
            result["body"]["text"], "Olá {{1}}, seu pedido {{2}} está pronto!"
        )

    def test_handles_empty_body(self):
        """Should handle payload without body."""
        translation_payload = {
            "header": {"header_type": "TEXT", "text": "Header"},
        }

        result = self.handler.convert_body_to_numeric_for_meta(translation_payload)

        self.assertNotIn("body", result)
        self.assertEqual(result["header"]["text"], "Header")

    def test_handles_body_without_text(self):
        """Should handle body dict without text key."""
        translation_payload = {
            "body": {"type": "BODY"},
        }

        result = self.handler.convert_body_to_numeric_for_meta(translation_payload)

        self.assertEqual(result["body"], {"type": "BODY"})

    def test_does_not_modify_original_payload(self):
        """Should return a copy, not modify the original."""
        translation_payload = {
            "body": {
                "type": "BODY",
                "text": "Olá {{client_name}}!",
            },
        }

        result = self.handler.convert_body_to_numeric_for_meta(translation_payload)

        # Original should remain unchanged
        self.assertEqual(translation_payload["body"]["text"], "Olá {{client_name}}!")
        # Result should have converted body
        self.assertEqual(result["body"]["text"], "Olá {{1}}!")

    def test_real_world_cart_abandonment_template(self):
        """Test with real cart abandonment template scenario."""
        translation_payload = {
            "body": {
                "type": "BODY",
                "text": (
                    "Olá {{cliente_name}}! 🛒\n"
                    "Você deixou itens no carrinho no valor de {{valor}}.\n"
                    "Finalize sua compra: {{link}}"
                ),
            },
            "header": {"header_type": "IMAGE", "text": "base64_image"},
            "buttons": [{"type": "URL", "text": "Finalizar"}],
        }

        result = self.handler.convert_body_to_numeric_for_meta(translation_payload)

        expected_body = (
            "Olá {{1}}! 🛒\n"
            "Você deixou itens no carrinho no valor de {{2}}.\n"
            "Finalize sua compra: {{3}}"
        )
        self.assertEqual(result["body"]["text"], expected_body)
        # Other fields should remain unchanged
        self.assertEqual(result["header"]["header_type"], "IMAGE")
        self.assertEqual(result["buttons"], [{"type": "URL", "text": "Finalizar"}])
