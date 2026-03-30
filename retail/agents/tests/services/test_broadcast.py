from django.test import TestCase

from unittest.mock import MagicMock, patch

from uuid import uuid4

from retail.agents.domains.agent_webhook.services.broadcast import Broadcast


class BroadcastHandlerTest(TestCase):
    """Test cases for BroadcastHandler service functionality."""

    def setUp(self):
        self.mock_flows_service = MagicMock()
        self.mock_audit = MagicMock()
        self.handler = Broadcast(
            flows_service=self.mock_flows_service, audit_func=self.mock_audit
        )
        self.mock_agent = MagicMock()
        self.mock_agent.uuid = uuid4()
        self.mock_agent.channel_uuid = uuid4()
        self.mock_agent.project.uuid = uuid4()
        self.mock_agent.config = None

    def test_can_send_to_contact_no_config(self):
        self.mock_agent.config = None
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_empty_config(self):
        self.mock_agent.config = {}
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_no_contact_urn(self):
        data = {}
        self.assertFalse(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_no_integration_settings(self):
        self.mock_agent.config = {"other_settings": {}}
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_no_order_status_restriction(self):
        self.mock_agent.config = {"integration_settings": {"other_restriction": {}}}
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_restriction_inactive(self):
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": False,
                    "allowed_phone_numbers": ["whatsapp:123"],
                }
            }
        }
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_restriction_active_allowed(self):
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": True,
                    "allowed_phone_numbers": ["whatsapp:123"],
                }
            }
        }
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_restriction_active_blocked(self):
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": True,
                    "allowed_phone_numbers": ["whatsapp:999"],
                }
            }
        }
        data = {"contact_urn": "whatsapp:123"}
        self.assertFalse(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_restriction_active_no_allowed_numbers(self):
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": True,
                    "allowed_phone_numbers": [],
                }
            }
        }
        data = {"contact_urn": "whatsapp:123"}
        self.assertFalse(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_restriction_active_missing_allowed_numbers(self):
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": True,
                }
            }
        }
        data = {"contact_urn": "whatsapp:123"}
        self.assertFalse(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_get_current_template_name_success(self):
        data = {"template": "order_update"}
        mock_template = MagicMock()
        mock_template.current_version.template_name = "order_update_v2"
        mock_template.current_version.status = "APPROVED"

        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_template
        self.mock_agent.templates.filter = MagicMock(return_value=mock_filter)

        result = self.handler.get_current_template(self.mock_agent, data)

        self.assertEqual(result, mock_template)
        self.mock_agent.templates.filter.assert_called_once()

    def test_get_current_template_name_not_found(self):
        data = {"template": "non_existent_template"}
        mock_filter = MagicMock()
        mock_filter.first.return_value = None
        self.mock_agent.templates.filter = MagicMock(return_value=mock_filter)

        result = self.handler.get_current_template(self.mock_agent, data)

        self.assertIsNone(result)

    def test_get_current_template_name_no_current_version(self):
        data = {"template": "order_update"}
        # Filter returns None when no template matches (because current_version__isnull=False filter)
        mock_filter = MagicMock()
        mock_filter.first.return_value = None
        self.mock_agent.templates.filter = MagicMock(return_value=mock_filter)

        result = self.handler.get_current_template(self.mock_agent, data)

        self.assertIsNone(result)

    def test_send_message(self):
        message = {"template": "test", "contact": "whatsapp:123"}
        mock_agent = MagicMock()
        lambda_data = {
            "status": 0,
            "template": "test",
            "contact_urn": "whatsapp:123",
            "template_variables": ["var1", "value1"],
        }

        self.handler.send_message(message, mock_agent, lambda_data)

        self.mock_flows_service.send_whatsapp_broadcast.assert_called_once_with(message)

    def test_build_message_success(self):
        data = {"template": "order_update", "contact_urn": "whatsapp:123"}
        mock_template = MagicMock()
        mock_template.current_version.template_name = "order_update_v2"
        mock_template.current_version.status = "APPROVED"

        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_template
        self.mock_agent.templates.filter = MagicMock(return_value=mock_filter)

        with patch.object(
            self.handler,
            "build_broadcast_template_message",
            return_value={"msg": "ok"},
        ) as mock_build:
            result = self.handler.build_message(self.mock_agent, data)

            self.assertEqual(result, {"msg": "ok"})
            mock_build.assert_called_once_with(
                data=data,
                channel_uuid=str(self.mock_agent.channel_uuid),
                project_uuid=str(self.mock_agent.project.uuid),
                template=mock_template,
            )

    def test_build_message_template_not_found(self):
        data = {"template": "non_existent_template"}
        mock_filter = MagicMock()
        mock_filter.first.return_value = None
        self.mock_agent.templates.filter = MagicMock(return_value=mock_filter)

        result = self.handler.build_message(self.mock_agent, data)

        self.assertIsNone(result)

    def test_register_broadcast_event_with_lambda_data(self):
        message = {
            "msg": {
                "template": {"name": "message_template", "variables": ["var1", "var2"]}
            },
            "urns": ["whatsapp:123456789"],
        }
        response = {"status": "success"}
        mock_agent = MagicMock()
        mock_agent.project.uuid = "project-uuid"
        mock_agent.agent.uuid = "agent-uuid"

        lambda_data = {
            "status": 0,
            "template": "lambda_template",
            "template_variables": ["var1", "value1", "var2", "value2"],
            "contact_urn": "whatsapp:987654321",
        }

        audit_calls = []

        def mock_audit_func(path, data):
            audit_calls.append(data)

        self.mock_audit.side_effect = mock_audit_func

        self.handler._register_broadcast_event(
            message, response, mock_agent, lambda_data
        )

        self.assertEqual(len(audit_calls), 1)
        event_data = audit_calls[0]

        self.assertEqual(event_data["status"], 0)
        self.assertEqual(event_data["template"], "lambda_template")
        self.assertEqual(event_data["contact_urn"], "whatsapp:987654321")
        self.assertEqual(event_data["template_variables"], {"1": "var1", "2": "var2"})
        self.assertEqual(event_data["project"], "project-uuid")
        self.assertEqual(event_data["agent"], "agent-uuid")
        self.assertEqual(event_data["request"], message)
        self.assertEqual(event_data["response"], response)
        self.assertEqual(event_data["data"], {"event_type": "template_broadcast_sent"})

    def test_register_broadcast_event_without_lambda_data(self):
        message = {
            "msg": {
                "template": {"name": "message_template", "variables": ["var1", "var2"]}
            },
            "urns": ["whatsapp:123456789"],
        }
        response = {"status": "success"}
        mock_agent = MagicMock()
        mock_agent.project.uuid = "project-uuid"
        mock_agent.agent.uuid = "agent-uuid"

        audit_calls = []

        def mock_audit_func(path, data):
            audit_calls.append(data)

        self.mock_audit.side_effect = mock_audit_func

        self.handler._register_broadcast_event(message, response, mock_agent, None)

        self.assertEqual(len(audit_calls), 1)
        event_data = audit_calls[0]

        self.assertNotIn("status", event_data)
        self.assertEqual(event_data["template"], "message_template")
        self.assertEqual(event_data["contact_urn"], "whatsapp:123456789")
        self.assertEqual(event_data["template_variables"], {"1": "var1", "2": "var2"})
        self.assertEqual(event_data["project"], "project-uuid")
        self.assertEqual(event_data["agent"], "agent-uuid")
        self.assertEqual(event_data["data"], {"event_type": "template_broadcast_sent"})

    def test_register_broadcast_event_with_error(self):
        message = {
            "msg": {
                "template": {"name": "message_template", "variables": ["var1", "var2"]}
            },
            "urns": ["whatsapp:123456789"],
        }
        response = {"error": "Some error occurred"}
        mock_agent = MagicMock()
        mock_agent.project.uuid = "project-uuid"
        mock_agent.agent.uuid = "agent-uuid"

        lambda_data = {
            "status": 2,
            "template": "lambda_template",
            "template_variables": ["var1", "value1"],
            "contact_urn": "whatsapp:987654321",
        }

        audit_calls = []

        def mock_audit_func(path, data):
            audit_calls.append(data)

        self.mock_audit.side_effect = mock_audit_func

        self.handler._register_broadcast_event(
            message, response, mock_agent, lambda_data
        )

        self.assertEqual(len(audit_calls), 1)
        event_data = audit_calls[0]

        self.assertEqual(event_data["status"], 2)
        self.assertEqual(event_data["error"], {"message": "Some error occurred"})
        self.assertEqual(event_data["data"], {"event_type": "template_broadcast_sent"})

    def test_register_broadcast_event_with_string_error(self):
        message = {
            "msg": {
                "template": {"name": "message_template", "variables": ["var1", "var2"]}
            },
            "urns": ["whatsapp:123456789"],
        }
        response = {"error": "Simple string error"}
        mock_agent = MagicMock()
        mock_agent.project.uuid = "project-uuid"
        mock_agent.agent.uuid = "agent-uuid"

        audit_calls = []

        def mock_audit_func(path, data):
            audit_calls.append(data)

        self.mock_audit.side_effect = mock_audit_func

        self.handler._register_broadcast_event(message, response, mock_agent, None)

        self.assertEqual(len(audit_calls), 1)
        event_data = audit_calls[0]

        self.assertEqual(event_data["error"], {"message": "Simple string error"})
        self.assertEqual(event_data["data"], {"event_type": "template_broadcast_sent"})

    def test_build_broadcast_template_message_with_order_details(self):
        """Includes interaction_type and order_details in msg when provided."""
        mock_template = MagicMock()
        mock_template.current_version.template_name = "payment_confirmation"
        mock_template.metadata = {}

        order_details = {
            "reference_id": "1234567890123-01",
            "payment_settings": {
                "type": "digital-goods",
                "payment_link": "https://example.com/checkout",
                "pix_config": {
                    "key": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "key_type": "EVP",
                    "merchant_name": "TestStore",
                    "code": "00020126580014br.gov.bcb.pix",
                },
            },
            "total_amount": 26489,
            "order": {
                "items": [
                    {
                        "retailer_id": "880032#1",
                        "name": "Tenis Nike Air Max 270",
                        "amount": {"value": 24990, "offset": 100},
                        "quantity": 1,
                    }
                ],
                "subtotal": 26988,
                "tax": {"description": "Impostos", "offset": 100, "value": 0},
                "discount": {"description": "Desconto", "offset": 100, "value": 999},
                "shipping": {"description": "Frete", "offset": 100, "value": 500},
            },
        }

        data = {
            "template_variables": {
                "1": "Thayna",
                "order_details": order_details,
            },
            "contact_urn": "whatsapp:555191269029",
            "language": "pt-BR",
        }

        result = self.handler.build_broadcast_template_message(
            data=data,
            channel_uuid="channel-uuid",
            project_uuid="project-uuid",
            template=mock_template,
        )

        self.assertEqual(result["msg"]["interaction_type"], "order_details")
        self.assertEqual(result["msg"]["order_details"], order_details)
        self.assertEqual(result["msg"]["template"]["variables"], ["Thayna"])
        self.assertEqual(result["msg"]["template"]["locale"], "pt-BR")

    def test_build_broadcast_template_message_without_order_details(self):
        """Does not include interaction_type or order_details when not provided."""
        mock_template = MagicMock()
        mock_template.current_version.template_name = "order_update"
        mock_template.metadata = {}

        data = {
            "template_variables": {"1": "Value1"},
            "contact_urn": "whatsapp:123",
        }

        result = self.handler.build_broadcast_template_message(
            data=data,
            channel_uuid="channel-uuid",
            project_uuid="project-uuid",
            template=mock_template,
        )

        self.assertNotIn("interaction_type", result["msg"])
        self.assertNotIn("order_details", result["msg"])

    def test_register_broadcast_event_with_order_details(self):
        """Includes interaction_type and order_details in audit event."""
        message = {
            "msg": {"template": {"name": "payment_template", "variables": ["var1"]}},
            "urns": ["whatsapp:123"],
        }
        response = {"status": "success"}
        mock_agent = MagicMock()
        mock_agent.project.uuid = "project-uuid"
        mock_agent.agent.uuid = "agent-uuid"

        order_details = {
            "reference_id": "ref-123",
            "total_amount": 10000,
        }
        lambda_data = {
            "status": 0,
            "template": "payment_template",
            "contact_urn": "whatsapp:123",
            "template_variables": {
                "1": "var1",
                "order_details": order_details,
            },
        }

        audit_calls = []

        def mock_audit_func(path, data):
            audit_calls.append(data)

        self.mock_audit.side_effect = mock_audit_func

        self.handler._register_broadcast_event(
            message, response, mock_agent, lambda_data
        )

        self.assertEqual(len(audit_calls), 1)
        event_data = audit_calls[0]

        self.assertEqual(event_data["interaction_type"], "order_details")
        self.assertEqual(event_data["order_details"], order_details)

    def test_register_broadcast_event_without_order_details(self):
        """Does not include interaction_type or order_details when not in lambda_data."""
        message = {
            "msg": {"template": {"name": "template", "variables": []}},
            "urns": ["whatsapp:123"],
        }
        response = {"status": "success"}
        mock_agent = MagicMock()
        mock_agent.project.uuid = "project-uuid"
        mock_agent.agent.uuid = "agent-uuid"

        lambda_data = {
            "status": 0,
            "template": "template",
            "contact_urn": "whatsapp:123",
        }

        audit_calls = []

        def mock_audit_func(path, data):
            audit_calls.append(data)

        self.mock_audit.side_effect = mock_audit_func

        self.handler._register_broadcast_event(
            message, response, mock_agent, lambda_data
        )

        event_data = audit_calls[0]

        self.assertNotIn("interaction_type", event_data)
        self.assertNotIn("order_details", event_data)

    def test_resolve_language_from_lambda_payload(self):
        """Language from Lambda payload takes priority."""
        mock_template = MagicMock()
        mock_template.metadata = {"language": "pt_BR"}
        data = {"language": "es-MX"}

        result = self.handler._resolve_language(data, mock_template)

        self.assertEqual(result, "es-MX")

    def test_resolve_language_from_template_metadata(self):
        """Falls back to template metadata when Lambda doesn't provide language."""
        mock_template = MagicMock()
        mock_template.metadata = {"language": "es_MX"}
        data = {}

        result = self.handler._resolve_language(data, mock_template)

        self.assertEqual(result, "es-MX")  # Converted from es_MX

    def test_resolve_language_converts_underscore_to_hyphen(self):
        """Converts Meta format (es_MX) to Flows API format (es-MX)."""
        mock_template = MagicMock()
        mock_template.metadata = {"language": "pt_BR"}
        data = {}

        result = self.handler._resolve_language(data, mock_template)

        self.assertEqual(result, "pt-BR")

    def test_resolve_language_returns_none_when_not_available(self):
        """Returns None when no language is available."""
        mock_template = MagicMock()
        mock_template.metadata = {}
        data = {}

        result = self.handler._resolve_language(data, mock_template)

        self.assertIsNone(result)

    def test_resolve_language_handles_none_metadata(self):
        """Handles template with None metadata gracefully."""
        mock_template = MagicMock()
        mock_template.metadata = None
        data = {}

        result = self.handler._resolve_language(data, mock_template)

        self.assertIsNone(result)
