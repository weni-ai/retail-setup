from django.test import TestCase

from unittest.mock import MagicMock, patch

from retail.agents.assign.models import IntegratedAgent
from retail.agents.webhooks.usecases.order_status_update import (
    AgentOrderStatusUpdateUsecase,
)
from retail.projects.models import Project
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


class AgentOrderStatusUpdateUsecaseTest(TestCase):
    def setUp(self):
        self.usecase = AgentOrderStatusUpdateUsecase()
        self.mock_project = MagicMock(spec=Project)
        self.mock_project.uuid = "project-uuid"
        self.mock_integrated_agent = MagicMock(spec=IntegratedAgent)
        self.mock_integrated_agent.uuid = "agent-uuid"
        self.mock_integrated_agent.ignore_templates = False

    @patch("retail.agents.webhooks.usecases.order_status_update.settings")
    @patch("retail.agents.webhooks.usecases.order_status_update.cache")
    @patch("retail.agents.webhooks.usecases.order_status_update.IntegratedAgent")
    def test_get_integrated_agent_if_exists_returns_from_cache(
        self, mock_integrated_agent_cls, mock_cache, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "uuid"
        mock_cache.get.return_value = self.mock_integrated_agent

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)
        self.assertEqual(result, self.mock_integrated_agent)
        mock_cache.get.assert_called_once()

    @patch("retail.agents.webhooks.usecases.order_status_update.settings")
    @patch("retail.agents.webhooks.usecases.order_status_update.cache")
    @patch("retail.agents.webhooks.usecases.order_status_update.IntegratedAgent")
    def test_get_integrated_agent_if_exists_fetches_and_sets_cache(
        self, mock_integrated_agent_cls, mock_cache, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "uuid"
        mock_cache.get.return_value = None
        mock_obj = MagicMock()
        mock_integrated_agent_cls.objects.get.return_value = mock_obj

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)
        self.assertEqual(result, mock_obj)
        mock_integrated_agent_cls.objects.get.assert_called_once()
        mock_cache.set.assert_called_once()

    @patch("retail.agents.webhooks.usecases.order_status_update.settings")
    @patch("retail.agents.webhooks.usecases.order_status_update.cache")
    @patch("retail.agents.webhooks.usecases.order_status_update.IntegratedAgent")
    def test_get_integrated_agent_if_exists_returns_none_if_not_found(
        self, mock_integrated_agent_cls, mock_cache, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "uuid"
        mock_cache.get.return_value = None
        does_not_exist = type("DoesNotExist", (Exception,), {})
        mock_integrated_agent_cls.DoesNotExist = does_not_exist
        mock_integrated_agent_cls.objects.get.side_effect = does_not_exist()

        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)
        self.assertIsNone(result)

    @patch("retail.agents.webhooks.usecases.order_status_update.settings")
    def test_get_integrated_agent_if_exists_returns_none_if_setting_missing(
        self, mock_settings
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = None
        result = self.usecase.get_integrated_agent_if_exists(self.mock_project)
        self.assertIsNone(result)

    @patch("retail.agents.webhooks.usecases.order_status_update.cache")
    @patch("retail.agents.webhooks.usecases.order_status_update.Project")
    def test_get_project_by_vtex_account_returns_from_cache(
        self, mock_project_cls, mock_cache
    ):
        mock_cache.get.return_value = self.mock_project
        result = self.usecase.get_project_by_vtex_account("vtex_account")
        self.assertEqual(result, self.mock_project)
        mock_cache.get.assert_called_once_with("project_by_vtex_account_vtex_account")

    @patch("retail.agents.webhooks.usecases.order_status_update.cache")
    @patch("retail.agents.webhooks.usecases.order_status_update.Project")
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
        mock_cache.set.assert_called_once()

    @patch("retail.agents.webhooks.usecases.order_status_update.cache")
    @patch("retail.agents.webhooks.usecases.order_status_update.Project")
    def test_get_project_by_vtex_account_returns_none_if_not_found(
        self, mock_project_cls, mock_cache
    ):
        mock_cache.get.return_value = None
        does_not_exist = type("DoesNotExist", (Exception,), {})
        mock_project_cls.DoesNotExist = does_not_exist
        mock_project_cls.objects.get.side_effect = does_not_exist()

        result = self.usecase.get_project_by_vtex_account("vtex_account")
        self.assertIsNone(result)

    @patch("retail.agents.webhooks.usecases.order_status_update.cache")
    @patch("retail.agents.webhooks.usecases.order_status_update.Project")
    def test_get_project_by_vtex_account_returns_none_if_multiple_found(
        self, mock_project_cls, mock_cache
    ):
        from django.core.exceptions import MultipleObjectsReturned

        mock_cache.get.return_value = None

        mock_project_cls.DoesNotExist = Exception
        mock_project_cls.MultipleObjectsReturned = MultipleObjectsReturned
        mock_project_cls.objects.get.side_effect = MultipleObjectsReturned()

        result = self.usecase.get_project_by_vtex_account("vtex_account")
        self.assertIsNone(result)

    @patch("retail.agents.webhooks.usecases.order_status_update.AgentWebhookUseCase")
    @patch("retail.agents.webhooks.usecases.order_status_update.RequestData")
    @patch(
        "retail.agents.webhooks.usecases.order_status_update.adapt_order_status_to_webhook_payload"
    )
    def test_execute_calls_agent_webhook_use_case(
        self, mock_adapt_payload, mock_request_data_cls, mock_agent_webhook_use_case_cls
    ):
        mock_order_status_dto = MagicMock(spec=OrderStatusDTO)
        mock_order_status_dto.orderId = "order-id"
        mock_adapt_payload.return_value = {"order": "payload"}
        mock_request_data = MagicMock()
        mock_request_data_cls.return_value = mock_request_data
        mock_agent_webhook_use_case = MagicMock()
        mock_agent_webhook_use_case_cls.return_value = mock_agent_webhook_use_case
        mock_agent_webhook_use_case._addapt_credentials.return_value = {"user": "john"}

        self.usecase.execute(self.mock_integrated_agent, mock_order_status_dto)

        mock_adapt_payload.assert_called_once_with(mock_order_status_dto)
        mock_request_data.set_credentials.assert_called_once_with({"user": "john"})
        mock_request_data.set_ignored_official_rules.assert_called_once_with(
            self.mock_integrated_agent.ignore_templates
        )
        mock_agent_webhook_use_case.execute.assert_called_once_with(
            self.mock_integrated_agent, mock_request_data
        )
