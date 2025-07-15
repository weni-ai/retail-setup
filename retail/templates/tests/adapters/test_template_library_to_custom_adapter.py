import base64

from django.test import TestCase
from unittest.mock import Mock

from retail.templates.adapters.template_library_to_custom_adapter import (
    HeaderTransformer,
    BodyTransformer,
    FooterTransformer,
    ButtonTransformer,
    TemplateTranslationAdapter,
)


class TestHeaderTransformer(TestCase):
    def setUp(self):
        self.transformer = HeaderTransformer()

    def test_transform_with_header(self):
        template_data = {"header": "Test Header"}
        result = self.transformer.transform(template_data)
        expected = {"header_type": "TEXT", "text": "Test Header"}
        self.assertEqual(result, expected)

    def test_transform_without_header(self):
        template_data = {}
        result = self.transformer.transform(template_data)
        self.assertIsNone(result)

    def test_transform_with_empty_header(self):
        template_data = {"header": ""}
        result = self.transformer.transform(template_data)
        self.assertIsNone(result)

    def test_transform_with_image_header(self):
        base_64_header = base64.b64encode("teste".encode("utf-8")).decode("utf-8")
        template_data = {"header": base_64_header}
        result = self.transformer.transform(template_data)
        expected = {"header_type": "IMAGE", "example": base_64_header}
        self.assertEqual(result, expected)

    def test_transform_with_already_translated_header(self):
        template_data = {"header": {"header_type": "TEXT", "text": "Already"}}
        result = self.transformer.transform(template_data)
        self.assertEqual(result, {"header_type": "TEXT", "text": "Already"})


class TestBodyTransformer(TestCase):
    def setUp(self):
        self.transformer = BodyTransformer()

    def test_transform_basic_body(self):
        template_data = {"body": "Test body message"}
        result = self.transformer.transform(template_data)
        expected = {"type": "BODY", "text": "Test body message"}
        self.assertEqual(result, expected)

    def test_transform_body_with_params(self):
        template_data = {"body": "Hello {{1}}", "body_params": ["John"]}
        result = self.transformer.transform(template_data)
        expected = {
            "type": "BODY",
            "text": "Hello {{1}}",
            "example": {"body_text": [["John"]]},
        }
        self.assertEqual(result, expected)

    def test_transform_without_body(self):
        template_data = {}
        result = self.transformer.transform(template_data)
        self.assertIsNone(result)

    def test_transform_with_empty_body(self):
        template_data = {"body": ""}
        result = self.transformer.transform(template_data)
        self.assertIsNone(result)


class TestFooterTransformer(TestCase):
    def setUp(self):
        self.transformer = FooterTransformer()

    def test_transform_with_footer(self):
        template_data = {"footer": "Test Footer"}
        result = self.transformer.transform(template_data)
        expected = {"type": "FOOTER", "text": "Test Footer"}
        self.assertEqual(result, expected)

    def test_transform_without_footer(self):
        template_data = {}
        result = self.transformer.transform(template_data)
        self.assertIsNone(result)

    def test_transform_with_empty_footer(self):
        template_data = {"footer": ""}
        result = self.transformer.transform(template_data)
        self.assertIsNone(result)


class TestButtonTransformer(TestCase):
    def setUp(self):
        self.transformer = ButtonTransformer()

    def test_transform_without_buttons(self):
        template_data = {}
        result = self.transformer.transform(template_data)
        self.assertIsNone(result)

    def test_transform_url_button_without_suffix(self):
        template_data = {
            "buttons": [
                {
                    "type": "URL",
                    "text": "Visit Website",
                    "url": {"base_url": "https://example.com"},
                }
            ]
        }
        result = self.transformer.transform(template_data)
        expected = [
            {"type": "URL", "text": "Visit Website", "url": "https://example.com"}
        ]
        self.assertEqual(result, expected)

    def test_transform_url_button_with_suffix(self):
        template_data = {
            "buttons": [
                {
                    "type": "URL",
                    "text": "Visit Product",
                    "url": {
                        "base_url": "https://example.com/product/",
                        "url_suffix_example": "123",
                    },
                }
            ]
        }
        result = self.transformer.transform(template_data)
        expected = [
            {
                "type": "URL",
                "text": "Visit Product",
                "url": "https://example.com/product/{{1}}",
                "example": ["123"],
            }
        ]
        self.assertEqual(result, expected)

    def test_transform_phone_button(self):
        template_data = {
            "buttons": [
                {
                    "type": "PHONE_NUMBER",
                    "text": "Call Us",
                    "phone_number": "1234567890",
                    "country_code": "1",
                }
            ]
        }
        result = self.transformer.transform(template_data)
        expected = [
            {
                "type": "PHONE_NUMBER",
                "text": "Call Us",
                "phone_number": "1234567890",
                "country_code": "1",
            }
        ]
        self.assertEqual(result, expected)

    def test_transform_phone_button_default_country_code(self):
        template_data = {
            "buttons": [
                {
                    "type": "PHONE_NUMBER",
                    "text": "Call Us",
                    "phone_number": "1234567890",
                }
            ]
        }
        result = self.transformer.transform(template_data)
        expected = [
            {
                "type": "PHONE_NUMBER",
                "text": "Call Us",
                "phone_number": "1234567890",
                "country_code": "55",
            }
        ]
        self.assertEqual(result, expected)

    def test_skip_already_translated_button(self):
        template_data = {
            "buttons": [
                {
                    "type": "URL",
                    "text": "Already Translated",
                    "url": "https://example.com",
                }
            ]
        }
        result = self.transformer.transform(template_data)
        self.assertEqual(result, [])

    def test_transform_button_with_unexpected_format(self):
        template_data = {
            "buttons": [
                {
                    "text": "No Type",
                    "url": {"base_url": "https://example.com"},
                }
            ]
        }

        with self.assertRaises(KeyError):
            self.transformer.transform(template_data)

    def test_is_button_format_already_translated(self):
        button = {"type": "URL", "url": "https://example.com"}
        self.assertTrue(self.transformer._is_button_format_already_translated(button))

        button = {"type": "URL", "url": {"base_url": "https://example.com"}}
        self.assertFalse(self.transformer._is_button_format_already_translated(button))


class TestTemplateTranslationAdapter(TestCase):
    def setUp(self):
        self.adapter = TemplateTranslationAdapter()

    def test_adapt_complete_template(self):
        template_data = {
            "language": "en_US",
            "header": "Welcome",
            "body": "Hello {{1}}",
            "body_params": ["John"],
            "footer": "Thank you",
            "buttons": [
                {
                    "type": "URL",
                    "text": "Visit Website",
                    "url": {"base_url": "https://example.com"},
                }
            ],
        }
        result = self.adapter.adapt(template_data)

        self.assertEqual(result["language"], "en_US")
        self.assertEqual(result["body"]["type"], "BODY")
        self.assertEqual(result["body"]["text"], "Hello {{1}}")
        self.assertEqual(result["body"]["example"], {"body_text": [["John"]]})
        self.assertEqual(result["header"]["header_type"], "TEXT")
        self.assertEqual(result["header"]["text"], "Welcome")
        self.assertEqual(result["footer"]["type"], "FOOTER")
        self.assertEqual(result["footer"]["text"], "Thank you")
        self.assertEqual(len(result["buttons"]), 1)
        self.assertEqual(result["buttons"][0]["type"], "URL")

    def test_adapt_minimal_template(self):
        template_data = {"body": "Simple message"}
        result = self.adapter.adapt(template_data)

        self.assertEqual(result["language"], "pt_BR")
        self.assertEqual(result["body"]["type"], "BODY")
        self.assertEqual(result["body"]["text"], "Simple message")
        self.assertNotIn("header", result)
        self.assertNotIn("footer", result)
        self.assertNotIn("buttons", result)

    def test_adapt_with_custom_transformers(self):
        mock_header = Mock()
        mock_body = Mock()
        mock_footer = Mock()
        mock_button = Mock()

        mock_header.transform.return_value = {
            "header_type": "TEXT",
            "text": "Custom Header",
        }
        mock_body.transform.return_value = {"type": "BODY", "text": "Custom Body"}
        mock_footer.transform.return_value = None
        mock_button.transform.return_value = None

        adapter = TemplateTranslationAdapter(
            header_transformer=mock_header,
            body_transformer=mock_body,
            footer_transformer=mock_footer,
            button_transformer=mock_button,
        )

        template_data = {"body": "Test"}
        result = adapter.adapt(template_data)

        mock_header.transform.assert_called_once_with(template_data)
        mock_body.transform.assert_called_once_with(template_data)
        mock_footer.transform.assert_called_once_with(template_data)
        mock_button.transform.assert_called_once_with(template_data)

        self.assertEqual(result["header"]["text"], "Custom Header")
        self.assertEqual(result["body"]["text"], "Custom Body")
        self.assertNotIn("footer", result)
        self.assertNotIn("buttons", result)

    def test_adapt_with_empty_fields(self):
        template_data = {"header": "", "footer": "", "body": ""}
        result = self.adapter.adapt(template_data)
        self.assertNotIn("header", result)
        self.assertNotIn("footer", result)
        self.assertNotIn("body", result)
        self.assertNotIn("buttons", result)
        self.assertEqual(result["language"], "pt_BR")
