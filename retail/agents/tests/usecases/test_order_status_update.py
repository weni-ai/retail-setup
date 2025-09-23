from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from rest_framework.exceptions import ValidationError

from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
    adapt_order_status_to_webhook_payload,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.projects.models import Project
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


class AgentOrderStatusUpdateUsecaseTest(TestCase):
    """Test cases for AgentOrderStatusUpdateUsecase functionality."""

    def setUp(self):
        self.usecase = AgentOrderStatusUpdateUsecase()
        self.mock_project = MagicMock(spec=Project)
        self.mock_project.uuid = uuid4()
        self.mock_integrated_agent = MagicMock(spec=IntegratedAgent)
        self.mock_integrated_agent.uuid = uuid4()
        self.mock_integrated_agent.ignore_templates = False

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    def test_get_integrated_agent_if_exists_returns_from_cache(
        self, mock_cache, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "test-agent-uuid"
        mock_cache.get.return_value = self.mock_integrated_agent

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertEqual(result, self.mock_integrated_agent)
        mock_cache.get.assert_called_once_with(
            f"order_status_agent_{str(self.mock_project.uuid)}"
        )

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.IntegratedAgent")
    def test_get_integrated_agent_if_exists_fetches_and_sets_cache(
        self, mock_integrated_agent_cls, mock_cache, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "test-agent-uuid"
        mock_cache.get.return_value = None
        mock_obj = MagicMock()
        mock_integrated_agent_cls.objects.get.return_value = mock_obj

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertEqual(result, mock_obj)
        mock_integrated_agent_cls.objects.get.assert_called_once_with(
            agent__uuid="test-agent-uuid",
            project=self.mock_project,
            is_active=True,
        )
        mock_cache.set.assert_called_once_with(
            f"order_status_agent_{str(self.mock_project.uuid)}",
            mock_obj,
            timeout=21600,
        )

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.IntegratedAgent")
    def test_get_integrated_agent_if_exists_returns_none_if_not_found(
        self, mock_integrated_agent_cls, mock_cache, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "test-agent-uuid"
        mock_cache.get.return_value = None

        # Create a proper exception class that inherits from BaseException
        does_not_exist_exception = type("DoesNotExist", (Exception,), {})
        mock_integrated_agent_cls.DoesNotExist = does_not_exist_exception

        # Both calls (official agent and parent_agent_uuid search) raise DoesNotExist
        mock_integrated_agent_cls.objects.get.side_effect = [
            does_not_exist_exception(),  # Official agent not found
            does_not_exist_exception(),  # Agent with parent_agent_uuid not found
        ]

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertIsNone(result)
        # Should be called twice: once for official agent, once for parent_agent_uuid search
        self.assertEqual(mock_integrated_agent_cls.objects.get.call_count, 2)

        # Verify the first call was for official agent
        first_call_args = mock_integrated_agent_cls.objects.get.call_args_list[0]
        self.assertEqual(first_call_args[1]["agent__uuid"], "test-agent-uuid")
        self.assertEqual(first_call_args[1]["project"], self.mock_project)
        self.assertEqual(first_call_args[1]["is_active"], True)

        # Verify the second call was for parent_agent_uuid search
        second_call_args = mock_integrated_agent_cls.objects.get.call_args_list[1]
        self.assertEqual(second_call_args[1]["parent_agent_uuid__isnull"], False)
        self.assertEqual(second_call_args[1]["project"], self.mock_project)
        self.assertEqual(second_call_args[1]["is_active"], True)

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.IntegratedAgent")
    def test_get_integrated_agent_if_exists_finds_agent_with_parent_agent_uuid(
        self, mock_integrated_agent_cls, mock_cache, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "test-agent-uuid"
        mock_cache.get.return_value = None

        # Mock official agent not found
        does_not_exist_exception = type("DoesNotExist", (Exception,), {})
        mock_integrated_agent_cls.DoesNotExist = does_not_exist_exception

        # First call (official agent) raises DoesNotExist
        # Second call (agent with parent_agent_uuid) returns a mock agent
        mock_agent_with_parent = MagicMock()
        mock_agent_with_parent.parent_agent_uuid = "parent-uuid-123"
        mock_integrated_agent_cls.objects.get.side_effect = [
            does_not_exist_exception(),  # Official agent not found
            mock_agent_with_parent,  # Agent with parent_agent_uuid found
        ]

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertEqual(result, mock_agent_with_parent)
        # Should be called twice: once for official agent, once for agent with parent_agent_uuid
        self.assertEqual(mock_integrated_agent_cls.objects.get.call_count, 2)

        # Verify the second call was for parent_agent_uuid__isnull=False
        second_call_args = mock_integrated_agent_cls.objects.get.call_args_list[1]
        self.assertEqual(second_call_args[1]["parent_agent_uuid__isnull"], False)
        self.assertEqual(second_call_args[1]["project"], self.mock_project)
        self.assertEqual(second_call_args[1]["is_active"], True)

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.IntegratedAgent")
    def test_get_integrated_agent_if_exists_raises_error_on_multiple_parent_agents(
        self, mock_integrated_agent_cls, mock_cache, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "test-agent-uuid"
        mock_cache.get.return_value = None

        # Mock official agent not found
        does_not_exist_exception = type("DoesNotExist", (Exception,), {})
        multiple_objects_exception = type("MultipleObjectsReturned", (Exception,), {})
        mock_integrated_agent_cls.DoesNotExist = does_not_exist_exception
        mock_integrated_agent_cls.MultipleObjectsReturned = multiple_objects_exception

        # First call (official agent) raises DoesNotExist
        # Second call (agents with parent_agent_uuid) raises MultipleObjectsReturned
        mock_integrated_agent_cls.objects.get.side_effect = [
            does_not_exist_exception(),  # Official agent not found
            multiple_objects_exception(),  # Multiple agents with parent_agent_uuid found
        ]

        with self.assertRaises(ValidationError) as context:
            self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertEqual(
            context.exception.detail["error"],
            "Multiple agents with parent_agent_uuid found for this project",
        )
        # The code is stored in the ErrorDetail object within detail
        self.assertEqual(
            context.exception.detail["error"].code, "multiple_parent_agents"
        )

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    def test_get_integrated_agent_if_exists_returns_none_if_setting_missing(
        self, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = None

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertIsNone(result)

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.Project")
    def test_get_project_by_vtex_account_returns_from_cache(
        self, mock_project_cls, mock_cache
    ):
        mock_cache.get.return_value = self.mock_project

        result = self.usecase.get_project_by_vtex_account("vtex_account")

        self.assertEqual(result, self.mock_project)
        mock_cache.get.assert_called_once_with("project_by_vtex_account_vtex_account")

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.Project")
    def test_get_project_by_vtex_account_fetches_and_sets_cache(
        self, mock_project_cls, mock_cache
    ):
        mock_cache.get.return_value = None
        mock_obj = MagicMock()
        mock_project_cls.objects.get.return_value = mock_obj

        result = self.usecase.get_project_by_vtex_account("vtex_account")

        self.assertEqual(result, mock_obj)
        mock_project_cls.objects.get.assert_called_once_with(
            vtex_account="vtex_account"
        )
        mock_cache.set.assert_called_once_with(
            "project_by_vtex_account_vtex_account", mock_obj, timeout=43200
        )

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.Project")
    def test_get_project_by_vtex_account_returns_none_if_not_found(
        self, mock_project_cls, mock_cache
    ):
        mock_cache.get.return_value = None

        # Create a proper exception class that inherits from BaseException
        does_not_exist_exception = type("DoesNotExist", (Exception,), {})
        mock_project_cls.DoesNotExist = does_not_exist_exception
        mock_project_cls.objects.get.side_effect = does_not_exist_exception()

        result = self.usecase.get_project_by_vtex_account("vtex_account")

        self.assertIsNone(result)
        mock_project_cls.objects.get.assert_called_once_with(
            vtex_account="vtex_account"
        )

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.Project")
    def test_get_project_by_vtex_account_returns_none_if_multiple_found(
        self, mock_project_cls, mock_cache
    ):
        mock_cache.get.return_value = None

        # Create a proper exception class that inherits from BaseException
        multiple_objects_returned_exception = type(
            "MultipleObjectsReturned", (Exception,), {}
        )
        mock_project_cls.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_project_cls.MultipleObjectsReturned = multiple_objects_returned_exception
        mock_project_cls.objects.get.side_effect = multiple_objects_returned_exception()

        result = self.usecase.get_project_by_vtex_account("vtex_account")

        self.assertIsNone(result)
        mock_project_cls.objects.get.assert_called_once_with(
            vtex_account="vtex_account"
        )

    @patch(
        "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase"
    )
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.RequestData")
    def test_execute_calls_agent_webhook_use_case(
        self, mock_request_data_cls, mock_agent_webhook_use_case_cls
    ):
        mock_order_status_dto = MagicMock(spec=OrderStatusDTO)
        mock_order_status_dto.orderId = "order-id"
        mock_order_status_dto.domain = "test-domain"
        mock_order_status_dto.currentState = "invoiced"
        mock_order_status_dto.lastState = "payment-approved"
        mock_order_status_dto.vtexAccount = "test-account"

        mock_request_data = MagicMock()
        mock_request_data_cls.return_value = mock_request_data
        mock_agent_webhook_use_case = MagicMock()
        mock_agent_webhook_use_case_cls.return_value = mock_agent_webhook_use_case
        mock_agent_webhook_use_case._addapt_credentials.return_value = {"user": "john"}

        self.usecase.execute(self.mock_integrated_agent, mock_order_status_dto)

        expected_payload = {
            "Domain": "test-domain",
            "OrderId": "order-id",
            "State": "invoiced",
            "LastState": "payment-approved",
            "Origin": {
                "Account": "test-account",
                "Sender": "Gallery",
            },
        }

        mock_request_data_cls.assert_called_once_with(
            params={},
            payload=expected_payload,
        )
        mock_request_data.set_credentials.assert_called_once_with({"user": "john"})
        mock_request_data.set_ignored_official_rules.assert_called_once_with(
            self.mock_integrated_agent.ignore_templates
        )
        mock_agent_webhook_use_case.execute.assert_called_once_with(
            self.mock_integrated_agent, mock_request_data
        )

    def test_adapt_order_status_to_webhook_payload(self):
        mock_order_status_dto = MagicMock(spec=OrderStatusDTO)
        mock_order_status_dto.domain = "test-domain"
        mock_order_status_dto.orderId = "order-123"
        mock_order_status_dto.currentState = "invoiced"
        mock_order_status_dto.lastState = "payment-approved"
        mock_order_status_dto.vtexAccount = "test-account"

        result = adapt_order_status_to_webhook_payload(mock_order_status_dto)

        expected = {
            "Domain": "test-domain",
            "OrderId": "order-123",
            "State": "invoiced",
            "LastState": "payment-approved",
            "Origin": {
                "Account": "test-account",
                "Sender": "Gallery",
            },
        }

        self.assertEqual(result, expected)

    def test_adapt_order_status_to_webhook_payload_with_none_values(self):
        mock_order_status_dto = MagicMock(spec=OrderStatusDTO)
        mock_order_status_dto.domain = None
        mock_order_status_dto.orderId = "order-123"
        mock_order_status_dto.currentState = None
        mock_order_status_dto.lastState = None
        mock_order_status_dto.vtexAccount = "test-account"

        result = adapt_order_status_to_webhook_payload(mock_order_status_dto)

        expected = {
            "Domain": None,
            "OrderId": "order-123",
            "State": None,
            "LastState": None,
            "Origin": {
                "Account": "test-account",
                "Sender": "Gallery",
            },
        }

        self.assertEqual(result, expected)
