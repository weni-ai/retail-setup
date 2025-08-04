from django.test import TestCase

from unittest.mock import Mock, patch

from retail.agents.utils import (
    build_broadcast_template_message,
    adapt_order_status_to_webhook_payload,
)
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO
from retail.templates.models import Template, Version
from retail.interfaces.services.aws_s3 import S3ServiceInterface


class TestBuildBroadcastTemplateMessage(TestCase):
    def setUp(self):
        self.channel_uuid = "3acb032f-c1db-4bd8-b33b-a43464a6accd"
        self.project_uuid = "95de8165-836e-4d9d-8ef4-abcf812cd546"
        self.create_mock_template = lambda name: self._create_mock_template(name)

    def _create_mock_template(self, template_name):
        mock_version = Mock(spec=Version)
        mock_version.template_name = template_name

        mock_template = Mock(spec=Template)
        mock_template.current_version = mock_version
        mock_template.metadata = {}

        return mock_template

    def test_message_without_button(self):
        data = {
            "template_variables": {"2": "12345", "1": "@contact.name"},
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        expected = {
            "project": self.project_uuid,
            "urns": ["whatsapp:5565992828858"],
            "channel": self.channel_uuid,
            "msg": {
                "template": {
                    "locale": "pt-BR",
                    "name": "order_confirmation",
                    "variables": ["@contact.name", "12345"],
                }
            },
        }

        template = self.create_mock_template("order_confirmation")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result, expected)

    def test_message_with_button(self):
        data = {
            "template_variables": {
                "1": "@contact.name",
                "button": "2960629205a149fd88f2d080d5affe25/",
            },
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        expected = {
            "project": self.project_uuid,
            "urns": ["whatsapp:5565992828858"],
            "channel": self.channel_uuid,
            "msg": {
                "template": {
                    "locale": "pt-BR",
                    "name": "abandoned_cart",
                    "variables": ["@contact.name"],
                },
                "buttons": [
                    {
                        "sub_type": "url",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "2960629205a149fd88f2d080d5affe25/",
                            }
                        ],
                    }
                ],
            },
        }

        template = self.create_mock_template("abandoned_cart")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result, expected)

    @patch("retail.agents.utils.logger")
    def test_non_numeric_keys_are_ignored_with_warning(self, mock_logger):
        data = {
            "template_variables": {"1": "a", "abc": "should_be_ignored", "2": "b"},
            "contact_urn": "whatsapp:123",
            "language": "en-US",
        }

        template = self.create_mock_template("test")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result["msg"]["template"]["variables"], ["a", "b"])
        mock_logger.warning.assert_called_once_with(
            "Ignoring non-numeric template variable key: abc"
        )

    def test_non_numeric_keys_are_ignored(self):
        data = {
            "template_variables": {"1": "a", "abc": "should_be_ignored", "2": "b"},
            "contact_urn": "whatsapp:123",
            "language": "en-US",
        }

        template = self.create_mock_template("test")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result["msg"]["template"]["variables"], ["a", "b"])

    def test_default_language_fallback(self):
        data = {
            "template_variables": {"1": "only"},
            "contact_urn": "whatsapp:123",
        }

        template = self.create_mock_template("test")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result["msg"]["template"]["locale"], "pt-BR")

    def test_missing_locale_keeps_structure(self):
        data = {
            "template_variables": {"1": "Hello"},
            "contact_urn": "whatsapp:123",
        }

        template = self.create_mock_template("missing_locale")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertIn("locale", result["msg"]["template"])
        self.assertEqual(result["msg"]["template"]["locale"], "pt-BR")

    def test_variable_ordering(self):
        data = {
            "template_variables": {"3": "third", "1": "first", "2": "second"},
            "contact_urn": "whatsapp:5511999999999",
            "language": "pt-BR",
        }

        template = self.create_mock_template("ordering_test")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )

        self.assertEqual(
            result["msg"]["template"]["variables"],
            ["first", "second", "third"],
            "Variables should be ordered by numeric key ascending",
        )

    def test_empty_variables(self):
        data = {
            "template_variables": {},
            "contact_urn": "whatsapp:999999999",
        }

        template = self.create_mock_template("empty_case")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result, {})

    @patch("retail.agents.utils.logger")
    def test_missing_required_fields_returns_empty_dict_with_error_log(
        self, mock_logger
    ):
        data = {"template_variables": {"1": "value"}}

        template = self.create_mock_template("test")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result, {})
        mock_logger.error.assert_called_once()
        error_call_args = mock_logger.error.call_args[0][0]
        self.assertIn("Incomplete message data", error_call_args)
        self.assertIn("Template: test", error_call_args)
        self.assertIn("URN: None", error_call_args)
        self.assertIn("Variables: ['value']", error_call_args)

    def test_missing_required_fields_returns_empty_dict(self):
        data = {"template_variables": {"1": "value"}}

        template = self.create_mock_template("test")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result, {})

    @patch("retail.agents.utils.logger")
    def test_missing_template_name_returns_empty_dict_with_error_log(self, mock_logger):
        data = {
            "template_variables": {"1": "value"},
            "contact_urn": "whatsapp:123",
        }

        mock_version = Mock(spec=Version)
        mock_version.template_name = ""
        mock_template = Mock(spec=Template)
        mock_template.current_version = mock_version
        mock_template.metadata = {}

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, mock_template
        )
        self.assertEqual(result, {})
        mock_logger.error.assert_called_once()
        error_call_args = mock_logger.error.call_args[0][0]
        self.assertIn("Incomplete message data", error_call_args)
        self.assertIn("Template: ", error_call_args)
        self.assertIn("URN: whatsapp:123", error_call_args)
        self.assertIn("Variables: ['value']", error_call_args)

    def test_missing_template_name_returns_empty_dict(self):
        data = {
            "template_variables": {"1": "value"},
            "contact_urn": "whatsapp:123",
        }

        mock_version = Mock(spec=Version)
        mock_version.template_name = ""
        mock_template = Mock(spec=Template)
        mock_template.current_version = mock_version
        mock_template.metadata = {}

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, mock_template
        )
        self.assertEqual(result, {})

    def test_missing_contact_urn_returns_empty_dict(self):
        data = {
            "template_variables": {"1": "value"},
            "language": "pt-BR",
        }

        template = self.create_mock_template("test_template")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result, {})

    def test_none_contact_urn_returns_empty_dict(self):
        data = {
            "template_variables": {"1": "value"},
            "contact_urn": None,
            "language": "pt-BR",
        }

        template = self.create_mock_template("test_template")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result, {})

    def test_none_template_name_returns_empty_dict(self):
        data = {
            "template_variables": {"1": "value"},
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        mock_version = Mock(spec=Version)
        mock_version.template_name = None
        mock_template = Mock(spec=Template)
        mock_template.current_version = mock_version
        mock_template.metadata = {}

        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, mock_template
        )
        self.assertEqual(result, {})

    def test_button_with_empty_string_is_ignored(self):
        data = {
            "template_variables": {
                "1": "test",
                "button": "",
            },
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        template = self.create_mock_template("test_template")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertNotIn("buttons", result["msg"])

    def test_button_with_none_is_ignored(self):
        data = {
            "template_variables": {
                "1": "test",
                "button": None,
            },
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        template = self.create_mock_template("test_template")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertNotIn("buttons", result["msg"])

    def test_mixed_numeric_and_non_numeric_keys(self):
        data = {
            "template_variables": {
                "1": "first",
                "invalid": "ignored",
                "3": "third",
                "another_invalid": "also_ignored",
                "2": "second",
            },
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        template = self.create_mock_template("test_template")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(
            result["msg"]["template"]["variables"], ["first", "second", "third"]
        )

    def test_numeric_keys_with_gaps(self):
        data = {
            "template_variables": {
                "1": "first",
                "5": "fifth",
                "3": "third",
            },
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        template = self.create_mock_template("test_template")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(
            result["msg"]["template"]["variables"], ["first", "third", "fifth"]
        )

    def test_template_variables_pop_button_modifies_original_dict(self):
        data = {
            "template_variables": {
                "1": "test",
                "button": "button_value",
            },
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        original_template_vars = data["template_variables"].copy()

        template = self.create_mock_template("test_template")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )

        self.assertNotIn("button", data["template_variables"])
        self.assertIn("button", original_template_vars)

        self.assertIn("buttons", result["msg"])
        self.assertEqual(
            result["msg"]["buttons"][0]["parameters"][0]["text"], "button_value"
        )

    def test_sorting_keys_with_different_numeric_values(self):
        data = {
            "template_variables": {
                "10": "tenth",
                "2": "second",
                "1": "first",
                "100": "hundredth",
            },
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        template = self.create_mock_template("test_template")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(
            result["msg"]["template"]["variables"],
            ["first", "second", "tenth", "hundredth"],
        )

    def test_message_structure_with_all_fields(self):
        data = {
            "template_variables": {
                "1": "variable1",
                "2": "variable2",
                "button": "button_url",
            },
            "contact_urn": "whatsapp:5511999999999",
            "language": "en-US",
        }

        template = self.create_mock_template("full_template")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )

        self.assertEqual(result["project"], self.project_uuid)
        self.assertEqual(result["urns"], ["whatsapp:5511999999999"])
        self.assertEqual(result["channel"], self.channel_uuid)
        self.assertEqual(result["msg"]["template"]["locale"], "en-US")
        self.assertEqual(result["msg"]["template"]["name"], "full_template")
        self.assertEqual(
            result["msg"]["template"]["variables"], ["variable1", "variable2"]
        )
        self.assertEqual(len(result["msg"]["buttons"]), 1)
        self.assertEqual(result["msg"]["buttons"][0]["sub_type"], "url")
        self.assertEqual(result["msg"]["buttons"][0]["parameters"][0]["type"], "text")
        self.assertEqual(
            result["msg"]["buttons"][0]["parameters"][0]["text"], "button_url"
        )

    def test_missing_template_variables_key(self):
        data = {
            "contact_urn": "whatsapp:123",
            "language": "pt-BR",
        }

        template = self.create_mock_template("test_template")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result, {})

    def test_empty_data_dict(self):
        data = {}

        template = self.create_mock_template("test_template")
        result = build_broadcast_template_message(
            data, self.channel_uuid, self.project_uuid, template
        )
        self.assertEqual(result, {})


class TestBuildBroadcastTemplateMessageWithImages(TestCase):
    def setUp(self):
        self.channel_uuid = "3acb032f-c1db-4bd8-b33b-a43464a6accd"
        self.project_uuid = "95de8165-836e-4d9d-8ef4-abcf812cd546"
        self.mock_s3_service = Mock(spec=S3ServiceInterface)
        self.mock_s3_service.generate_presigned_url.return_value = (
            "https://s3.amazonaws.com/bucket/test-image.jpg?signature=abc123"
        )

        self.mock_version = Mock(spec=Version)
        self.mock_version.template_name = "test_template"

        self.mock_template = Mock(spec=Template)
        self.mock_template.current_version = self.mock_version

    def test_message_with_image_header_creates_attachments_jpeg(self):
        self.mock_template.metadata = {
            "header": {"header_type": "IMAGE", "text": "images/header/test-image.jpg"}
        }

        data = {
            "template_variables": {"1": "test variable"},
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data,
            self.channel_uuid,
            self.project_uuid,
            self.mock_template,
            self.mock_s3_service,
        )

        self.assertIn("attachments", result["msg"])
        self.assertEqual(len(result["msg"]["attachments"]), 1)
        self.assertEqual(
            result["msg"]["attachments"][0],
            "image/jpeg:https://s3.amazonaws.com/bucket/test-image.jpg?signature=abc123",
        )

        self.mock_s3_service.generate_presigned_url.assert_called_once_with(
            "images/header/test-image.jpg"
        )

    def test_message_with_image_header_creates_attachments_png(self):
        self.mock_template.metadata = {
            "header": {"header_type": "IMAGE", "text": "images/header/test-image.png"}
        }

        data = {
            "template_variables": {"1": "test variable"},
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data,
            self.channel_uuid,
            self.project_uuid,
            self.mock_template,
            self.mock_s3_service,
        )

        self.assertIn("attachments", result["msg"])
        self.assertEqual(
            result["msg"]["attachments"][0],
            "image/png:https://s3.amazonaws.com/bucket/test-image.jpg?signature=abc123",
        )

    def test_message_with_image_header_jpg_converted_to_jpeg(self):
        self.mock_template.metadata = {
            "header": {"header_type": "IMAGE", "text": "images/header/test-image.jpg"}
        }

        data = {
            "template_variables": {"1": "test variable"},
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data,
            self.channel_uuid,
            self.project_uuid,
            self.mock_template,
            self.mock_s3_service,
        )

        self.assertTrue(result["msg"]["attachments"][0].startswith("image/jpeg:"))

    @patch("retail.agents.utils.logger")
    def test_message_with_unknown_image_type_uses_jpeg_fallback(self, mock_logger):
        self.mock_template.metadata = {
            "header": {
                "header_type": "IMAGE",
                "text": "images/header/test-file.unknown",
            }
        }

        data = {
            "template_variables": {"1": "test variable"},
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data,
            self.channel_uuid,
            self.project_uuid,
            self.mock_template,
            self.mock_s3_service,
        )

        self.assertEqual(
            result["msg"]["attachments"][0],
            "image/jpeg:https://s3.amazonaws.com/bucket/test-image.jpg?signature=abc123",
        )

        mock_logger.warning.assert_called_once_with(
            "Could not detect image type for images/header/test-file.unknown, using jpeg as fallback"
        )

    def test_message_with_no_header_no_attachments(self):
        self.mock_template.metadata = {}

        data = {
            "template_variables": {"1": "test variable"},
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data,
            self.channel_uuid,
            self.project_uuid,
            self.mock_template,
            self.mock_s3_service,
        )

        self.assertNotIn("attachments", result["msg"])

        self.mock_s3_service.generate_presigned_url.assert_not_called()

    def test_message_with_text_header_no_attachments(self):
        self.mock_template.metadata = {
            "header": {"header_type": "TEXT", "text": "Texto do header"}
        }

        data = {
            "template_variables": {"1": "test variable"},
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data,
            self.channel_uuid,
            self.project_uuid,
            self.mock_template,
            self.mock_s3_service,
        )

        self.assertNotIn("attachments", result["msg"])

        self.mock_s3_service.generate_presigned_url.assert_not_called()

    def test_message_with_image_header_and_button(self):
        self.mock_template.metadata = {
            "header": {"header_type": "IMAGE", "text": "images/header/test-image.gif"}
        }

        data = {
            "template_variables": {"1": "test variable", "button": "button_url"},
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data,
            self.channel_uuid,
            self.project_uuid,
            self.mock_template,
            self.mock_s3_service,
        )

        self.assertIn("attachments", result["msg"])
        self.assertIn("buttons", result["msg"])

        self.assertEqual(
            result["msg"]["attachments"][0],
            "image/gif:https://s3.amazonaws.com/bucket/test-image.jpg?signature=abc123",
        )

        self.assertEqual(
            result["msg"]["buttons"][0]["parameters"][0]["text"], "button_url"
        )

    def test_message_with_none_s3_key_no_attachments(self):
        self.mock_template.metadata = {"header": {"header_type": "IMAGE", "text": None}}

        data = {
            "template_variables": {"1": "test variable"},
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        result = build_broadcast_template_message(
            data,
            self.channel_uuid,
            self.project_uuid,
            self.mock_template,
            self.mock_s3_service,
        )

        self.assertNotIn("attachments", result["msg"])

        self.mock_s3_service.generate_presigned_url.assert_not_called()

    def test_message_uses_default_s3_service_when_none_provided(self):
        self.mock_template.metadata = {
            "header": {"header_type": "IMAGE", "text": "images/header/test-image.png"}
        }

        data = {
            "template_variables": {"1": "test variable"},
            "contact_urn": "whatsapp:5565992828858",
            "language": "pt-BR",
        }

        with patch("retail.agents.utils.S3Service") as mock_s3_service_class:
            mock_s3_instance = Mock(spec=S3ServiceInterface)
            mock_s3_instance.generate_presigned_url.return_value = (
                "https://s3.test.com/image.png"
            )
            mock_s3_service_class.return_value = mock_s3_instance

            result = build_broadcast_template_message(
                data, self.channel_uuid, self.project_uuid, self.mock_template
            )

            mock_s3_service_class.assert_called_once()

            self.assertIn("attachments", result["msg"])
            mock_s3_instance.generate_presigned_url.assert_called_once_with(
                "images/header/test-image.png"
            )


class TestAdaptOrderStatusToWebhookPayload(TestCase):
    def test_adapt_order_status_to_webhook_payload(self):
        order_status_dto = OrderStatusDTO(
            domain="test.domain.com",
            orderId="12345",
            currentState="invoiced",
            lastState="payment-approved",
            vtexAccount="testaccount",
            recorder="test_recorder",
            currentChangeDate="2023-01-01T00:00:00Z",
            lastChangeDate="2023-01-01T00:00:00Z",
        )

        expected = {
            "Domain": "test.domain.com",
            "OrderId": "12345",
            "State": "invoiced",
            "LastState": "payment-approved",
            "Origin": {
                "Account": "testaccount",
                "Sender": "Gallery",
            },
        }

        result = adapt_order_status_to_webhook_payload(order_status_dto)
        self.assertEqual(result, expected)

    def test_adapt_order_status_with_empty_values(self):
        order_status_dto = OrderStatusDTO(
            domain="",
            orderId="",
            currentState="",
            lastState="",
            vtexAccount="",
            recorder="",
            currentChangeDate="",
            lastChangeDate="",
        )

        expected = {
            "Domain": "",
            "OrderId": "",
            "State": "",
            "LastState": "",
            "Origin": {
                "Account": "",
                "Sender": "Gallery",
            },
        }

        result = adapt_order_status_to_webhook_payload(order_status_dto)
        self.assertEqual(result, expected)

    def test_adapt_order_status_with_none_values(self):
        order_status_dto = OrderStatusDTO(
            domain=None,
            orderId=None,
            currentState=None,
            lastState=None,
            vtexAccount=None,
            recorder=None,
            currentChangeDate=None,
            lastChangeDate=None,
        )

        expected = {
            "Domain": None,
            "OrderId": None,
            "State": None,
            "LastState": None,
            "Origin": {
                "Account": None,
                "Sender": "Gallery",
            },
        }

        result = adapt_order_status_to_webhook_payload(order_status_dto)
        self.assertEqual(result, expected)

    def test_adapt_order_status_sender_is_always_gallery(self):
        order_status_dto = OrderStatusDTO(
            domain="test.domain.com",
            orderId="12345",
            currentState="invoiced",
            lastState="payment-approved",
            vtexAccount="testaccount",
            recorder="test_recorder",
            currentChangeDate="2023-01-01T00:00:00Z",
            lastChangeDate="2023-01-01T00:00:00Z",
        )

        result = adapt_order_status_to_webhook_payload(order_status_dto)
        self.assertEqual(result["Origin"]["Sender"], "Gallery")

    def test_adapt_order_status_complete_payload_structure(self):
        order_status_dto = OrderStatusDTO(
            domain="example.vtexcommercestable.com.br",
            orderId="ORD-987654321",
            currentState="ready-for-handling",
            lastState="payment-pending",
            vtexAccount="examplestore",
            recorder="vtex_system",
            currentChangeDate="2023-12-01T10:30:00Z",
            lastChangeDate="2023-12-01T09:15:00Z",
        )

        result = adapt_order_status_to_webhook_payload(order_status_dto)

        self.assertIn("Domain", result)
        self.assertIn("OrderId", result)
        self.assertIn("State", result)
        self.assertIn("LastState", result)
        self.assertIn("Origin", result)

        self.assertIn("Account", result["Origin"])
        self.assertIn("Sender", result["Origin"])

        self.assertEqual(result["Domain"], "example.vtexcommercestable.com.br")
        self.assertEqual(result["OrderId"], "ORD-987654321")
        self.assertEqual(result["State"], "ready-for-handling")
        self.assertEqual(result["LastState"], "payment-pending")
        self.assertEqual(result["Origin"]["Account"], "examplestore")
        self.assertEqual(result["Origin"]["Sender"], "Gallery")

    def test_adapt_order_status_only_uses_required_dto_fields(self):
        order_status_dto = OrderStatusDTO(
            domain="test.domain.com",
            orderId="12345",
            currentState="invoiced",
            lastState="payment-approved",
            vtexAccount="testaccount",
            recorder="test_recorder",
            currentChangeDate="2023-01-01T00:00:00Z",
            lastChangeDate="2023-01-01T00:00:00Z",
        )

        result = adapt_order_status_to_webhook_payload(order_status_dto)

        expected_keys = {"Domain", "OrderId", "State", "LastState", "Origin"}
        self.assertEqual(set(result.keys()), expected_keys)

        self.assertNotIn("recorder", result)
        self.assertNotIn("currentChangeDate", result)
        self.assertNotIn("lastChangeDate", result)
        self.assertNotIn("Recorder", result)
        self.assertNotIn("CurrentChangeDate", result)
        self.assertNotIn("LastChangeDate", result)
