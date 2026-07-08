from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase
from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.usecases.delivered_order_tracking import (
    DeliveredOrderTrackingWebhookUseCase,
)


class DeliveredOrderTrackingWebhookUseCaseTest(TestCase):
    def setUp(self):
        self.use_case = DeliveredOrderTrackingWebhookUseCase()
        self.agent_uuid = str(uuid4())
        self.mock_integrated_agent = MagicMock(spec=IntegratedAgent)
        self.mock_integrated_agent.uuid = self.agent_uuid
        self.mock_integrated_agent.project.vtex_account = "testaccount"
        self.mock_integrated_agent.config = {
            "delivered_order_tracking": {"is_enabled": True}
        }

    @patch(
        "retail.agents.domains.agent_integration.usecases.delivered_order_tracking.IntegratedAgent"
    )
    def test_get_integrated_agent_found(self, mock_model):
        mock_model.objects.select_related.return_value.get.return_value = (
            self.mock_integrated_agent
        )

        result = self.use_case.get_integrated_agent(self.agent_uuid)

        self.assertEqual(result, self.mock_integrated_agent)
        mock_model.objects.select_related.assert_called_once_with("project")
        mock_model.objects.select_related.return_value.get.assert_called_once_with(
            uuid=self.agent_uuid,
            is_active=True,
        )

    @patch(
        "retail.agents.domains.agent_integration.usecases.delivered_order_tracking.IntegratedAgent"
    )
    def test_get_integrated_agent_not_found(self, mock_model):
        mock_model.DoesNotExist = IntegratedAgent.DoesNotExist
        mock_model.objects.select_related.return_value.get.side_effect = (
            IntegratedAgent.DoesNotExist
        )

        with self.assertRaises(NotFound):
            self.use_case.get_integrated_agent(self.agent_uuid)
