from unittest.mock import MagicMock
from uuid import uuid4

from django.test import SimpleTestCase

from retail.agents.domains.agent_integration.usecases.ensure_back_in_stock_contact_group import (
    BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME,
    EnsureBackInStockContactGroupUseCase,
)


class EnsureBackInStockContactGroupUseCaseTest(SimpleTestCase):
    def setUp(self):
        self.mock_flows = MagicMock()
        self.use_case = EnsureBackInStockContactGroupUseCase(
            flows_service=self.mock_flows
        )
        self.project_uuid = uuid4()

    def test_logs_and_skips_create_when_group_exists(self):
        self.mock_flows.get_contact_groups.return_value = {
            "results": [{"uuid": "g1", "name": BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME}]
        }

        with self.assertLogs(
            "retail.agents.domains.agent_integration.usecases."
            "ensure_back_in_stock_contact_group",
            level="INFO",
        ) as logs:
            self.use_case.execute(self.project_uuid)

        self.mock_flows.create_contact_group.assert_not_called()
        self.assertIn("Contact group already exists", " ".join(logs.output))

    def test_creates_group_when_missing(self):
        self.mock_flows.get_contact_groups.return_value = {"results": []}
        self.mock_flows.create_contact_group.return_value = {
            "uuid": "g1",
            "name": BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME,
        }

        with self.assertLogs(
            "retail.agents.domains.agent_integration.usecases."
            "ensure_back_in_stock_contact_group",
            level="INFO",
        ) as logs:
            self.use_case.execute(self.project_uuid)

        self.mock_flows.create_contact_group.assert_called_once_with(
            project_uuid=str(self.project_uuid),
            name=BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME,
        )
        self.assertIn("Contact group created", " ".join(logs.output))

    def test_skips_create_when_list_fails(self):
        self.mock_flows.get_contact_groups.return_value = None

        with self.assertLogs(
            "retail.agents.domains.agent_integration.usecases."
            "ensure_back_in_stock_contact_group",
            level="WARNING",
        ) as logs:
            self.use_case.execute(self.project_uuid)

        self.mock_flows.create_contact_group.assert_not_called()
        self.assertIn("list_failed", " ".join(logs.output))

    def test_warns_when_create_fails(self):
        self.mock_flows.get_contact_groups.return_value = {"results": []}
        self.mock_flows.create_contact_group.return_value = None

        with self.assertLogs(
            "retail.agents.domains.agent_integration.usecases."
            "ensure_back_in_stock_contact_group",
            level="WARNING",
        ) as logs:
            self.use_case.execute(self.project_uuid)

        self.assertIn("Contact group was not created", " ".join(logs.output))

    def test_does_not_raise_when_flows_service_blows_up(self):
        self.mock_flows.get_contact_groups.side_effect = RuntimeError("boom")

        with self.assertLogs(
            "retail.agents.domains.agent_integration.usecases."
            "ensure_back_in_stock_contact_group",
            level="ERROR",
        ) as logs:
            self.use_case.execute(self.project_uuid)

        self.mock_flows.create_contact_group.assert_not_called()
        self.assertIn("Failed to ensure contact group", " ".join(logs.output))
