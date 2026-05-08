from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from rest_framework.exceptions import ValidationError

from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
    adapt_order_status_to_webhook_payload,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.shared.cache import AgentRole
from retail.projects.models import Project
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


class AgentOrderStatusUpdateUsecaseTest(TestCase):
    """Test cases for AgentOrderStatusUpdateUsecase functionality."""

    def setUp(self):
        self.mock_cache_handler = MagicMock()
        self.usecase = AgentOrderStatusUpdateUsecase(
            cache_handler=self.mock_cache_handler
        )
        self.mock_project = MagicMock(spec=Project)
        self.mock_project.uuid = uuid4()
        self.mock_integrated_agent = MagicMock(spec=IntegratedAgent)
        self.mock_integrated_agent.uuid = uuid4()
        self.mock_integrated_agent.project_id = 12345
        self.mock_integrated_agent.ignore_templates = False

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    def test_get_integrated_agent_if_exists_returns_from_cache(self, mock_settings):
        mock_settings.ORDER_STATUS_AGENT_UUID = "test-agent-uuid"
        self.mock_cache_handler.get_role_agent.return_value = self.mock_integrated_agent

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertEqual(result, self.mock_integrated_agent)
        self.mock_cache_handler.get_role_agent.assert_called_once_with(
            self.mock_project.uuid, AgentRole.ORDER_STATUS
        )
        self.mock_cache_handler.set_role_agent.assert_not_called()

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.IntegratedAgent")
    def test_get_integrated_agent_if_exists_fetches_and_sets_cache(
        self, mock_integrated_agent_cls, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "test-agent-uuid"
        self.mock_cache_handler.get_role_agent.return_value = None
        mock_obj = MagicMock()
        mock_integrated_agent_cls.objects.get.return_value = mock_obj

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertEqual(result, mock_obj)
        mock_integrated_agent_cls.objects.get.assert_called_once_with(
            agent__uuid="test-agent-uuid",
            project=self.mock_project,
            is_active=True,
        )
        self.mock_cache_handler.set_role_agent.assert_called_once_with(
            mock_obj, AgentRole.ORDER_STATUS
        )

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.IntegratedAgent")
    def test_get_integrated_agent_if_exists_returns_none_if_not_found(
        self, mock_integrated_agent_cls, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "test-agent-uuid"
        self.mock_cache_handler.get_role_agent.return_value = None

        does_not_exist_exception = type("DoesNotExist", (Exception,), {})
        mock_integrated_agent_cls.DoesNotExist = does_not_exist_exception
        mock_integrated_agent_cls.objects.get.side_effect = [
            does_not_exist_exception(),
            does_not_exist_exception(),
        ]

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertIsNone(result)
        self.assertEqual(mock_integrated_agent_cls.objects.get.call_count, 2)
        self.mock_cache_handler.set_role_agent.assert_not_called()

        first_call_args = mock_integrated_agent_cls.objects.get.call_args_list[0]
        self.assertEqual(first_call_args[1]["agent__uuid"], "test-agent-uuid")
        self.assertEqual(first_call_args[1]["project"], self.mock_project)
        self.assertEqual(first_call_args[1]["is_active"], True)

        second_call_args = mock_integrated_agent_cls.objects.get.call_args_list[1]
        self.assertEqual(second_call_args[1]["parent_agent_uuid__isnull"], False)
        self.assertEqual(second_call_args[1]["project"], self.mock_project)
        self.assertEqual(second_call_args[1]["is_active"], True)

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.IntegratedAgent")
    def test_get_integrated_agent_if_exists_finds_agent_with_parent_agent_uuid(
        self, mock_integrated_agent_cls, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "test-agent-uuid"
        self.mock_cache_handler.get_role_agent.return_value = None

        does_not_exist_exception = type("DoesNotExist", (Exception,), {})
        mock_integrated_agent_cls.DoesNotExist = does_not_exist_exception

        mock_agent_with_parent = MagicMock()
        mock_agent_with_parent.parent_agent_uuid = "parent-uuid-123"
        mock_integrated_agent_cls.objects.get.side_effect = [
            does_not_exist_exception(),
            mock_agent_with_parent,
        ]

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertEqual(result, mock_agent_with_parent)
        self.assertEqual(mock_integrated_agent_cls.objects.get.call_count, 2)
        self.mock_cache_handler.set_role_agent.assert_called_once_with(
            mock_agent_with_parent, AgentRole.ORDER_STATUS
        )

        second_call_args = mock_integrated_agent_cls.objects.get.call_args_list[1]
        self.assertEqual(second_call_args[1]["parent_agent_uuid__isnull"], False)
        self.assertEqual(second_call_args[1]["project"], self.mock_project)
        self.assertEqual(second_call_args[1]["is_active"], True)

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.IntegratedAgent")
    def test_get_integrated_agent_if_exists_raises_error_on_multiple_parent_agents(
        self, mock_integrated_agent_cls, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "test-agent-uuid"
        self.mock_cache_handler.get_role_agent.return_value = None

        does_not_exist_exception = type("DoesNotExist", (Exception,), {})
        multiple_objects_exception = type("MultipleObjectsReturned", (Exception,), {})
        mock_integrated_agent_cls.DoesNotExist = does_not_exist_exception
        mock_integrated_agent_cls.MultipleObjectsReturned = multiple_objects_exception
        mock_integrated_agent_cls.objects.get.side_effect = [
            does_not_exist_exception(),
            multiple_objects_exception(),
        ]

        with self.assertRaises(ValidationError) as context:
            self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertEqual(
            context.exception.detail["error"],
            "Multiple agents with parent_agent_uuid found for this project",
        )
        self.assertEqual(
            context.exception.detail["error"].code, "multiple_parent_agents"
        )

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    def test_get_integrated_agent_returns_none_if_setting_missing(self, mock_settings):
        mock_settings.ORDER_STATUS_AGENT_UUID = None

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)

        self.assertIsNone(result)
        self.mock_cache_handler.get_role_agent.assert_not_called()

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

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch(
        "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase"
    )
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.RequestData")
    def test_execute_calls_agent_webhook_use_case(
        self,
        mock_request_data_cls,
        mock_agent_webhook_use_case_cls,
        mock_cache,
        mock_settings,
    ):
        mock_settings.ORDER_STATUS_DUPLICATE_WINDOW_SECONDS = 60
        mock_cache.add.return_value = True

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
                "Sender": "order-status-api",
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

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch(
        "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase"
    )
    def test_execute_skips_duplicate_event_within_window(
        self, mock_agent_webhook_use_case_cls, mock_cache, mock_settings
    ):
        mock_settings.ORDER_STATUS_DUPLICATE_WINDOW_SECONDS = 60
        mock_cache.add.return_value = False

        mock_order_status_dto = MagicMock(spec=OrderStatusDTO)
        mock_order_status_dto.orderId = "order-id"
        mock_order_status_dto.currentState = "invoiced"
        mock_order_status_dto.vtexAccount = "test-account"

        mock_agent_webhook_use_case = MagicMock()
        mock_agent_webhook_use_case_cls.return_value = mock_agent_webhook_use_case

        self.usecase.execute(self.mock_integrated_agent, mock_order_status_dto)

        mock_agent_webhook_use_case_cls.assert_not_called()
        mock_agent_webhook_use_case.execute.assert_not_called()

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch(
        "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase"
    )
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.RequestData")
    def test_execute_uses_cache_key_with_all_required_components(
        self,
        mock_request_data_cls,
        mock_agent_webhook_use_case_cls,
        mock_cache,
        mock_settings,
    ):
        mock_settings.ORDER_STATUS_DUPLICATE_WINDOW_SECONDS = 90
        mock_cache.add.return_value = True

        mock_order_status_dto = MagicMock(spec=OrderStatusDTO)
        mock_order_status_dto.orderId = "1628250823413-01"
        mock_order_status_dto.currentState = "order-created"
        mock_order_status_dto.lastState = "not-started"
        mock_order_status_dto.domain = "Marketplace"
        mock_order_status_dto.vtexAccount = "citerol"

        mock_agent_webhook_use_case_cls.return_value._addapt_credentials.return_value = (
            {}
        )

        self.usecase.execute(self.mock_integrated_agent, mock_order_status_dto)

        expected_cache_key = (
            f"order_status_event:"
            f"{self.mock_integrated_agent.project_id}:"
            f"{self.mock_integrated_agent.uuid}:"
            f"1628250823413-01:"
            f"order-created"
        )
        mock_cache.add.assert_called_once_with(
            expected_cache_key,
            1,
            timeout=90,
        )

    @patch("retail.agents.domains.agent_webhook.usecases.order_status.settings")
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.cache")
    @patch(
        "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase"
    )
    @patch("retail.agents.domains.agent_webhook.usecases.order_status.RequestData")
    def test_execute_different_states_produce_different_cache_keys(
        self,
        mock_request_data_cls,
        mock_agent_webhook_use_case_cls,
        mock_cache,
        mock_settings,
    ):
        mock_settings.ORDER_STATUS_DUPLICATE_WINDOW_SECONDS = 60
        mock_cache.add.return_value = True
        mock_agent_webhook_use_case_cls.return_value._addapt_credentials.return_value = (
            {}
        )

        first_dto = MagicMock(spec=OrderStatusDTO)
        first_dto.orderId = "order-1"
        first_dto.currentState = "approve-payment"
        first_dto.lastState = "payment-pending"
        first_dto.domain = "Marketplace"
        first_dto.vtexAccount = "test-account"

        second_dto = MagicMock(spec=OrderStatusDTO)
        second_dto.orderId = "order-1"
        second_dto.currentState = "payment-approved"
        second_dto.lastState = "approve-payment"
        second_dto.domain = "Marketplace"
        second_dto.vtexAccount = "test-account"

        self.usecase.execute(self.mock_integrated_agent, first_dto)
        self.usecase.execute(self.mock_integrated_agent, second_dto)

        self.assertEqual(mock_cache.add.call_count, 2)
        first_key = mock_cache.add.call_args_list[0][0][0]
        second_key = mock_cache.add.call_args_list[1][0][0]
        self.assertNotEqual(first_key, second_key)
        self.assertTrue(first_key.endswith(":approve-payment"))
        self.assertTrue(second_key.endswith(":payment-approved"))

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
                "Sender": "order-status-api",
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
                "Sender": "order-status-api",
            },
        }

        self.assertEqual(result, expected)
