from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.usecases.webhook import (
    AgentWebhookUseCase,
)
from retail.agents.tests.mocks.cache.integrated_agent_webhook import (
    IntegratedAgentCacheHandlerMock,
)


class AgentWebhookUseCaseTest(TestCase):
    """Test cases for AgentWebhookUseCase functionality."""

    def setUp(self):
        patcher = patch("weni_datalake_sdk.clients.client.send_commerce_webhook_data")
        self.mock_audit = patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_lambda_handler = MagicMock()
        self.mock_broadcast_handler = MagicMock()
        self.mock_cache_handler = IntegratedAgentCacheHandlerMock()

        self.usecase = AgentWebhookUseCase(
            active_agent=self.mock_lambda_handler,
            broadcast=self.mock_broadcast_handler,
            cache=self.mock_cache_handler,
        )
        self.mock_agent = MagicMock()
        self.mock_agent.uuid = uuid4()
        self.mock_agent.ignore_templates = False
        self.mock_agent.project.uuid = uuid4()
        self.mock_agent.project.vtex_account = "test_account"
        self.mock_agent.agent.lambda_arn = (
            "arn:aws:lambda:region:account-id:function:function-name"
        )
        self.mock_agent.channel_uuid = uuid4()
        self.mock_agent.contact_percentage = 100
        self.mock_agent.config = None
        self.mock_agent.templates.get.return_value.current_version.template_name = (
            "template_v1"
        )
        self.mock_agent.credentials.all.return_value = []

    def test_should_send_broadcast_100_percent(self):
        self.mock_agent.contact_percentage = 100
        self.assertTrue(self.usecase._should_send_broadcast(self.mock_agent))

    def test_should_not_send_broadcast_0_percent(self):
        self.mock_agent.contact_percentage = 0
        self.assertFalse(self.usecase._should_send_broadcast(self.mock_agent))

    def test_should_not_send_broadcast_none_percent(self):
        self.mock_agent.contact_percentage = None
        self.assertFalse(self.usecase._should_send_broadcast(self.mock_agent))

    def test_should_not_send_broadcast_negative_percent(self):
        self.mock_agent.contact_percentage = -10
        self.assertFalse(self.usecase._should_send_broadcast(self.mock_agent))

    def test_should_send_broadcast_random(self):
        self.mock_agent.contact_percentage = 50
        with patch("random.randint", return_value=25):
            self.assertTrue(self.usecase._should_send_broadcast(self.mock_agent))
        with patch("random.randint", return_value=75):
            self.assertFalse(self.usecase._should_send_broadcast(self.mock_agent))

    def test_addapt_credentials(self):
        cred1 = MagicMock()
        cred1.key = "user"
        cred1.value = "john"
        cred2 = MagicMock()
        cred2.key = "pass"
        cred2.value = "doe"
        self.mock_agent.credentials.all.return_value = [cred1, cred2]
        creds = self.usecase._addapt_credentials(self.mock_agent)
        self.assertEqual(creds, {"user": "john", "pass": "doe"})

    def test_addapt_credentials_empty(self):
        self.mock_agent.credentials.all.return_value = []
        creds = self.usecase._addapt_credentials(self.mock_agent)
        self.assertEqual(creds, {})

    def test_get_integrated_agent_blocked_uuid(self):
        blocked_uuid = "d30bcce8-ce67-4677-8a33-c12b62a51d4f"
        result = self.usecase._get_integrated_agent(blocked_uuid)
        self.assertIsNone(result)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects"
    )
    def test_get_integrated_agent_found(self, mock_objects):
        """Test successful retrieval of integrated agent with optimized queries."""
        mock_agent = MagicMock()
        test_uuid = uuid4()

        mock_queryset = MagicMock()
        mock_objects.select_related.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset
        mock_queryset.get.return_value = mock_agent

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_objects.select_related.assert_called_once_with("project", "agent")
        mock_queryset.get.assert_called_once_with(uuid=test_uuid, is_active=True)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects"
    )
    def test_get_integrated_agent_not_found(self, mock_objects):
        """Test handling of non-existent integrated agent."""
        test_uuid = uuid4()

        mock_queryset = MagicMock()
        mock_objects.select_related.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset
        mock_queryset.get.side_effect = IntegratedAgent.DoesNotExist()

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertIsNone(result)
        mock_objects.select_related.assert_called_once_with("project", "agent")
        mock_queryset.get.assert_called_once_with(uuid=test_uuid, is_active=True)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects"
    )
    def test_get_integrated_agent_from_cache(self, mock_objects):
        """Test that cached agent is returned without database query."""
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid

        self.mock_cache_handler.set_cached_agent(mock_agent)

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_objects.select_related.assert_not_called()

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects"
    )
    def test_get_integrated_agent_cache_miss_then_set(self, mock_objects):
        """Test cache miss scenario with subsequent cache setting."""
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid

        mock_queryset = MagicMock()
        mock_objects.select_related.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset
        mock_queryset.get.return_value = mock_agent

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_objects.select_related.assert_called_once_with("project", "agent")
        mock_queryset.get.assert_called_once_with(uuid=test_uuid, is_active=True)
        cached_agent = self.mock_cache_handler.get_cached_agent(test_uuid)
        self.assertEqual(cached_agent, mock_agent)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects"
    )
    def test_get_integrated_agent_cache_miss_not_found(self, mock_objects):
        """Test cache miss with non-existent agent."""
        test_uuid = uuid4()

        mock_queryset = MagicMock()
        mock_objects.select_related.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset
        mock_queryset.get.side_effect = IntegratedAgent.DoesNotExist()

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertIsNone(result)
        mock_objects.select_related.assert_called_once_with("project", "agent")
        mock_queryset.get.assert_called_once_with(uuid=test_uuid, is_active=True)
        cached_agent = self.mock_cache_handler.get_cached_agent(test_uuid)
        self.assertIsNone(cached_agent)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects"
    )
    def test_get_integrated_agent_cache_with_none_value(self, mock_objects):
        """Test cache with None value (cache miss scenario)."""
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid

        mock_queryset = MagicMock()
        mock_objects.select_related.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset
        mock_queryset.get.return_value = mock_agent

        self.mock_cache_handler.cache[str(test_uuid)] = None

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_objects.select_related.assert_called_once_with("project", "agent")
        mock_queryset.get.assert_called_once_with(uuid=test_uuid, is_active=True)
        cached_agent = self.mock_cache_handler.get_cached_agent(test_uuid)
        self.assertEqual(cached_agent, mock_agent)

    def test_get_integrated_agent_blocked_uuid_no_cache_interaction(self):
        """Test blocked UUID handling without cache interaction."""
        blocked_uuid = "d30bcce8-ce67-4677-8a33-c12b62a51d4f"

        result = self.usecase._get_integrated_agent(blocked_uuid)

        self.assertIsNone(result)
        cached_agent = self.mock_cache_handler.get_cached_agent(blocked_uuid)
        self.assertIsNone(cached_agent)

    def test_execute_successful(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}

        result = self.usecase.execute(self.mock_agent, MagicMock())

        self.assertIsNone(result)
        self.mock_broadcast_handler.send_message.assert_called_once()

    def test_execute_should_not_send_broadcast(self):
        self.mock_agent.contact_percentage = 0
        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_missing_template_error(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "error": "Missing template"
        }
        self.mock_lambda_handler.validate_response.return_value = False

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_template_not_active(self):
        self.mock_agent.templates.get.return_value.is_active = False
        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_contact_not_allowed(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = False

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_lambda_error_message(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "errorMessage": "Some error"
        }
        self.mock_lambda_handler.validate_response.return_value = False

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_template_not_found(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "not_found",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = None

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_build_message_exception(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.side_effect = Exception(
            "Build message error"
        )

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_build_message_returns_none(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = None

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)
        self.mock_broadcast_handler.send_message.assert_not_called()

    def test_execute_build_message_returns_empty_dict(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {}

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)
        self.mock_broadcast_handler.send_message.assert_not_called()

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects"
    )
    def test_get_integrated_agent_from_cache(self, mock_objects):
        """Test that cached agent is returned without database query."""
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid

        self.mock_cache_handler.set_cached_agent(mock_agent)

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_objects.select_related.assert_not_called()

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects"
    )
    def test_get_integrated_agent_cache_miss_then_set(self, mock_objects):
        """Test cache miss scenario with subsequent cache setting and optimized queries."""
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid

        mock_queryset = MagicMock()
        mock_objects.select_related.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset
        mock_queryset.get.return_value = mock_agent

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_objects.select_related.assert_called_once_with("project", "agent")
        mock_queryset.get.assert_called_once_with(uuid=test_uuid, is_active=True)
        cached_agent = self.mock_cache_handler.get_cached_agent(test_uuid)
        self.assertEqual(cached_agent, mock_agent)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects"
    )
    def test_get_integrated_agent_cache_miss_not_found(self, mock_objects):
        """Test cache miss with non-existent agent using optimized queries."""
        test_uuid = uuid4()

        mock_queryset = MagicMock()
        mock_objects.select_related.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset
        mock_queryset.get.side_effect = IntegratedAgent.DoesNotExist()

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertIsNone(result)
        mock_objects.select_related.assert_called_once_with("project", "agent")
        mock_queryset.get.assert_called_once_with(uuid=test_uuid, is_active=True)
        cached_agent = self.mock_cache_handler.get_cached_agent(test_uuid)
        self.assertIsNone(cached_agent)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects"
    )
    def test_get_integrated_agent_cache_with_none_value(self, mock_objects):
        """Test cache with None value (cache miss scenario) using optimized queries."""
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid

        mock_queryset = MagicMock()
        mock_objects.select_related.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset
        mock_queryset.get.return_value = mock_agent

        self.mock_cache_handler.cache[str(test_uuid)] = None

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_objects.select_related.assert_called_once_with("project", "agent")
        mock_queryset.get.assert_called_once_with(uuid=test_uuid, is_active=True)
        cached_agent = self.mock_cache_handler.get_cached_agent(test_uuid)
        self.assertEqual(cached_agent, mock_agent)

    def test_get_integrated_agent_blocked_uuid_no_cache_interaction(self):
        """Test blocked UUID handling without cache interaction."""
        blocked_uuid = "d30bcce8-ce67-4677-8a33-c12b62a51d4f"

        result = self.usecase._get_integrated_agent(blocked_uuid)

        self.assertIsNone(result)
        cached_agent = self.mock_cache_handler.get_cached_agent(blocked_uuid)
        self.assertIsNone(cached_agent)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects"
    )
    def test_optimized_queries_are_used(self, mock_objects):
        """Test that the optimized queries with select_related and prefetch_related are being used."""
        mock_agent = MagicMock()
        test_uuid = uuid4()

        mock_queryset = MagicMock()
        mock_objects.select_related.return_value = mock_queryset
        mock_queryset.prefetch_related.return_value = mock_queryset
        mock_queryset.get.return_value = mock_agent

        result = self.usecase._get_integrated_agent(test_uuid)

        mock_objects.select_related.assert_called_once_with("project", "agent")
        mock_queryset.prefetch_related.assert_called_once()

        prefetch_call_args = mock_queryset.prefetch_related.call_args[0]
        self.assertEqual(len(prefetch_call_args), 2)
        self.assertEqual(prefetch_call_args[1], "credentials")

        self.assertEqual(result, mock_agent)
