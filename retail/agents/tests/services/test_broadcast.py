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

    def test_normalize_template_variables_converts_labeled_to_numeric(self):
        """Should convert labeled variables to numeric based on template body."""
        mock_template = MagicMock()
        mock_template.name = "cart_abandonment"
        mock_template.metadata = {
            "body": "Olá {{client_name}}, seu pedido {{order_id}} no valor {{valor}}"
        }

        variables = {
            "client_name": "João Silva",
            "order_id": "12345",
            "valor": "R$ 299,90",
        }

        result, unknown = self.handler._normalize_template_variables(
            variables, mock_template
        )

        self.assertEqual(result["1"], "João Silva")
        self.assertEqual(result["2"], "12345")
        self.assertEqual(result["3"], "R$ 299,90")
        self.assertEqual(unknown, [])

    def test_normalize_template_variables_preserves_special_keys(self):
        """Should preserve button and image_url keys."""
        mock_template = MagicMock()
        mock_template.name = "cart_abandonment"
        mock_template.metadata = {"body": "Olá {{client_name}}"}

        variables = {
            "client_name": "João",
            "button": "cart/123",
            "image_url": "https://img.com/img.png",
        }

        result, unknown = self.handler._normalize_template_variables(
            variables, mock_template
        )

        self.assertEqual(result["1"], "João")
        self.assertEqual(result["button"], "cart/123")
        self.assertEqual(result["image_url"], "https://img.com/img.png")
        self.assertEqual(unknown, [])

    def test_normalize_template_variables_returns_unknown_labels(self):
        """Should return unknown variable labels not found in template."""
        mock_template = MagicMock()
        mock_template.name = "cart_abandonment"
        mock_template.metadata = {"body": "Olá {{client_name}}"}

        variables = {
            "client_name": "João",
            "unknown_var": "value",
        }

        result, unknown = self.handler._normalize_template_variables(
            variables, mock_template
        )

        self.assertEqual(result["1"], "João")
        self.assertIn("unknown_var", unknown)

    def test_normalize_template_variables_already_numeric(self):
        """Should return variables as-is when already numeric."""
        mock_template = MagicMock()
        mock_template.name = "cart_abandonment"
        mock_template.metadata = {"body": "Olá {{1}}, pedido {{2}}"}

        variables = {"1": "João", "2": "12345"}

        result, unknown = self.handler._normalize_template_variables(
            variables, mock_template
        )

        self.assertEqual(result["1"], "João")
        self.assertEqual(result["2"], "12345")
        self.assertEqual(unknown, [])

    def test_normalize_template_variables_legacy_agent_retrocompatibility(self):
        """
        Retrocompatibility: Legacy agents that return numeric variables
        (e.g., {"1": "value", "2": "value"}) should continue working.
        The system should NOT try to convert them.
        """
        mock_template = MagicMock()
        mock_template.name = "order_status"
        # Template body has labeled vars, but lambda sends numeric (legacy behavior)
        mock_template.metadata = {"body": "Olá {{client_name}}, pedido {{order_id}}"}

        # Legacy agent sends numeric variables
        legacy_variables = {
            "1": "João Silva",
            "2": "ORD-12345",
            "button": "https://track.com/ORD-12345",
            "image_url": "https://img.com/product.jpg",
        }

        result, unknown = self.handler._normalize_template_variables(
            legacy_variables, mock_template
        )

        # Should return exactly as received - no conversion
        self.assertEqual(result["1"], "João Silva")
        self.assertEqual(result["2"], "ORD-12345")
        self.assertEqual(result["button"], "https://track.com/ORD-12345")
        self.assertEqual(result["image_url"], "https://img.com/product.jpg")
        self.assertEqual(unknown, [])

    def test_normalize_template_variables_empty_body(self):
        """Should return variables as-is when template has no body."""
        mock_template = MagicMock()
        mock_template.name = "cart_abandonment"
        mock_template.metadata = {}

        variables = {"client_name": "João"}

        result, unknown = self.handler._normalize_template_variables(
            variables, mock_template
        )

        self.assertEqual(result["client_name"], "João")
        self.assertEqual(unknown, [])

    def test_normalize_template_variables_empty_variables(self):
        """Should handle empty variables dict."""
        mock_template = MagicMock()
        mock_template.metadata = {"body": "Olá {{client_name}}"}

        result, unknown = self.handler._normalize_template_variables({}, mock_template)

        self.assertEqual(result, {})
        self.assertEqual(unknown, [])

    def test_sort_variables_by_position(self):
        """Should sort variables by numeric position."""
        variables = {"2": "second", "1": "first", "3": "third"}

        result = self.handler._sort_variables_by_position(variables)

        self.assertEqual(result, ["first", "second", "third"])

    def test_sort_variables_by_position_ignores_non_numeric(self):
        """Should ignore non-numeric keys."""
        variables = {"2": "second", "1": "first", "button": "ignored"}

        result = self.handler._sort_variables_by_position(variables)

        self.assertEqual(result, ["first", "second"])

    def test_sort_variables_by_position_empty(self):
        """Should handle empty dict."""
        result = self.handler._sort_variables_by_position({})
        self.assertEqual(result, [])

    def test_build_broadcast_template_message_with_labeled_variables(self):
        """Should convert labeled variables when building broadcast message."""
        mock_template = MagicMock()
        mock_template.name = "cart_abandonment"
        mock_template.current_version.template_name = "weni_cart_abandonment_123"
        mock_template.metadata = {"body": "Olá {{client_name}}, pedido {{order_id}}"}

        data = {
            "template_variables": {
                "client_name": "João Silva",
                "order_id": "12345",
            },
            "contact_urn": "whatsapp:5584999999999",
        }

        result = self.handler.build_broadcast_template_message(
            data=data,
            channel_uuid=str(uuid4()),
            project_uuid=str(uuid4()),
            template=mock_template,
        )

        # Variables should be converted to list in correct order
        self.assertEqual(
            result["msg"]["template"]["variables"], ["João Silva", "12345"]
        )

    def test_build_broadcast_template_message_with_numeric_variables(self):
        """Should work with already numeric variables."""
        mock_template = MagicMock()
        mock_template.name = "cart_abandonment"
        mock_template.current_version.template_name = "weni_cart_abandonment_123"
        mock_template.metadata = {"body": "Olá {{1}}, pedido {{2}}"}

        data = {
            "template_variables": {
                "1": "João Silva",
                "2": "12345",
            },
            "contact_urn": "whatsapp:5584999999999",
        }

        result = self.handler.build_broadcast_template_message(
            data=data,
            channel_uuid=str(uuid4()),
            project_uuid=str(uuid4()),
            template=mock_template,
        )

        self.assertEqual(
            result["msg"]["template"]["variables"], ["João Silva", "12345"]
        )


class TestLambdaResponseSimulation(TestCase):
    """
    Tests simulating real lambda responses for both legacy and new agents.
    These tests validate the complete flow from lambda response to broadcast message.
    """

    def setUp(self):
        self.mock_flows_service = MagicMock()
        self.mock_audit = MagicMock()
        self.handler = Broadcast(
            flows_service=self.mock_flows_service, audit_func=self.mock_audit
        )

    def _create_mock_template(self, name, body, template_name=None):
        """Helper to create mock template."""
        mock_template = MagicMock()
        mock_template.name = name
        mock_template.current_version.template_name = (
            template_name or f"weni_{name}_123"
        )
        mock_template.metadata = {"body": body}
        return mock_template

    def test_lambda_response_legacy_format_cart_abandonment(self):
        """
        Simulates a LEGACY agent lambda response for cart abandonment.
        Legacy agents return numeric variables: {"1": "value", "2": "value"}
        """
        # Template with labeled variables in body
        template_body = (
            "Olá {{client_name}}! Você deixou itens no carrinho "
            "no valor de {{valor}}. Finalize sua compra: {{link}}"
        )
        mock_template = self._create_mock_template(
            name="cart_abandonment",
            body=template_body,
        )

        # LEGACY lambda response - uses numeric keys
        legacy_lambda_response = {
            "status": 0,
            "template": "cart_abandonment",
            "contact_urn": "whatsapp:5584999999999",
            "template_variables": {
                "1": "Maria Silva",
                "2": "R$ 299,90",
                "3": "https://loja.com/cart/abc123",
                "button": "cart/abc123",
                "image_url": "https://loja.com/img/produto.jpg",
            },
        }

        result = self.handler.build_broadcast_template_message(
            data=legacy_lambda_response,
            channel_uuid=str(uuid4()),
            project_uuid=str(uuid4()),
            template=mock_template,
        )

        # Verify message structure
        self.assertEqual(result["urns"], ["whatsapp:5584999999999"])
        self.assertEqual(result["msg"]["template"]["name"], "weni_cart_abandonment_123")

        # Variables should be in correct order
        self.assertEqual(
            result["msg"]["template"]["variables"],
            ["Maria Silva", "R$ 299,90", "https://loja.com/cart/abc123"],
        )

        # Button should be included
        self.assertEqual(
            result["msg"]["buttons"][0]["parameters"][0]["text"], "cart/abc123"
        )

        # Image attachment should be included
        self.assertIn("attachments", result["msg"])
        self.assertIn(
            "image/jpeg:https://loja.com/img/produto.jpg",
            result["msg"]["attachments"][0],
        )

    def test_lambda_response_new_format_cart_abandonment(self):
        """
        Simulates a NEW agent lambda response for cart abandonment.
        New agents return labeled variables: {"client_name": "value", "valor": "value"}
        """
        # Template with labeled variables in body
        template_body = (
            "Olá {{client_name}}! Você deixou itens no carrinho "
            "no valor de {{valor}}. Finalize sua compra: {{link}}"
        )
        mock_template = self._create_mock_template(
            name="cart_abandonment",
            body=template_body,
        )

        # NEW lambda response - uses labeled keys
        new_lambda_response = {
            "status": 0,
            "template": "cart_abandonment",
            "contact_urn": "whatsapp:5584999999999",
            "template_variables": {
                "client_name": "Maria Silva",
                "valor": "R$ 299,90",
                "link": "https://loja.com/cart/abc123",
                "button": "cart/abc123",
                "image_url": "https://loja.com/img/produto.jpg",
            },
        }

        result = self.handler.build_broadcast_template_message(
            data=new_lambda_response,
            channel_uuid=str(uuid4()),
            project_uuid=str(uuid4()),
            template=mock_template,
        )

        # Verify message structure
        self.assertEqual(result["urns"], ["whatsapp:5584999999999"])
        self.assertEqual(result["msg"]["template"]["name"], "weni_cart_abandonment_123")

        # Variables should be converted and in correct order based on body
        # body: "{{client_name}}...{{valor}}...{{link}}" → client_name=1, valor=2, link=3
        self.assertEqual(
            result["msg"]["template"]["variables"],
            ["Maria Silva", "R$ 299,90", "https://loja.com/cart/abc123"],
        )

        # Button should be included
        self.assertEqual(
            result["msg"]["buttons"][0]["parameters"][0]["text"], "cart/abc123"
        )

    def test_lambda_response_legacy_format_order_status(self):
        """
        Simulates a LEGACY agent lambda response for order status.
        """
        mock_template = self._create_mock_template(
            name="order_delivered",
            body="Olá {{1}}! Seu pedido {{2}} foi entregue em {{3}}.",
        )

        legacy_lambda_response = {
            "status": 0,
            "template": "order_delivered",
            "contact_urn": "whatsapp:5511988887777",
            "template_variables": {
                "1": "João Santos",
                "2": "PED-2024-001",
                "3": "06/02/2026 às 14:30",
            },
        }

        result = self.handler.build_broadcast_template_message(
            data=legacy_lambda_response,
            channel_uuid=str(uuid4()),
            project_uuid=str(uuid4()),
            template=mock_template,
        )

        self.assertEqual(
            result["msg"]["template"]["variables"],
            ["João Santos", "PED-2024-001", "06/02/2026 às 14:30"],
        )
        self.assertNotIn("buttons", result["msg"])
        self.assertNotIn("attachments", result["msg"])

    def test_lambda_response_new_format_order_status(self):
        """
        Simulates a NEW agent lambda response for order status.
        """
        mock_template = self._create_mock_template(
            name="order_delivered",
            body="Olá {{client_name}}! Seu pedido {{order_id}} foi entregue em {{delivery_date}}.",
        )

        new_lambda_response = {
            "status": 0,
            "template": "order_delivered",
            "contact_urn": "whatsapp:5511988887777",
            "template_variables": {
                "client_name": "João Santos",
                "order_id": "PED-2024-001",
                "delivery_date": "06/02/2026 às 14:30",
            },
        }

        result = self.handler.build_broadcast_template_message(
            data=new_lambda_response,
            channel_uuid=str(uuid4()),
            project_uuid=str(uuid4()),
            template=mock_template,
        )

        # Variables converted based on body order: client_name=1, order_id=2, delivery_date=3
        self.assertEqual(
            result["msg"]["template"]["variables"],
            ["João Santos", "PED-2024-001", "06/02/2026 às 14:30"],
        )

    def test_lambda_response_both_formats_produce_same_result(self):
        """
        Verifies that both legacy and new format produce the SAME broadcast message.
        This ensures retrocompatibility.
        """
        mock_template = self._create_mock_template(
            name="payment_confirmed",
            body="{{client_name}}, pagamento de {{valor}} confirmado! Pedido: {{order_id}}",
        )
        channel_uuid = str(uuid4())
        project_uuid = str(uuid4())

        # Legacy format
        legacy_response = {
            "contact_urn": "whatsapp:5584999999999",
            "template_variables": {
                "1": "Ana Paula",
                "2": "R$ 150,00",
                "3": "ORD-999",
            },
        }

        # New format
        new_response = {
            "contact_urn": "whatsapp:5584999999999",
            "template_variables": {
                "client_name": "Ana Paula",
                "valor": "R$ 150,00",
                "order_id": "ORD-999",
            },
        }

        legacy_result = self.handler.build_broadcast_template_message(
            data=legacy_response,
            channel_uuid=channel_uuid,
            project_uuid=project_uuid,
            template=mock_template,
        )

        new_result = self.handler.build_broadcast_template_message(
            data=new_response,
            channel_uuid=channel_uuid,
            project_uuid=project_uuid,
            template=mock_template,
        )

        # Both should produce the same variables list
        self.assertEqual(
            legacy_result["msg"]["template"]["variables"],
            new_result["msg"]["template"]["variables"],
        )
        self.assertEqual(
            legacy_result["msg"]["template"]["variables"],
            ["Ana Paula", "R$ 150,00", "ORD-999"],
        )

    def test_lambda_response_new_format_with_unknown_variable(self):
        """
        Tests that unknown variables in new format are logged but don't break the flow.
        """
        mock_template = self._create_mock_template(
            name="simple_template",
            body="Olá {{client_name}}!",
        )

        # Lambda sends extra variable not in template
        response_with_unknown = {
            "contact_urn": "whatsapp:5584999999999",
            "template_variables": {
                "client_name": "Test User",
                "unknown_var": "should be ignored",
            },
        }

        result = self.handler.build_broadcast_template_message(
            data=response_with_unknown,
            channel_uuid=str(uuid4()),
            project_uuid=str(uuid4()),
            template=mock_template,
        )

        # Should still work, only mapping known variables
        self.assertEqual(result["msg"]["template"]["variables"], ["Test User"])
