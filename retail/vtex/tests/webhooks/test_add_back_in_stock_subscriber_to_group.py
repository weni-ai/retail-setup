from unittest.mock import MagicMock
from uuid import uuid4

from django.test import SimpleTestCase

from retail.agents.domains.agent_integration.usecases.ensure_back_in_stock_contact_group import (
    BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME,
)
from retail.services.flows.service import FlowsContactUrnAlreadyExistsError
from retail.webhooks.vtex.usecases.add_back_in_stock_subscriber_to_group import (
    AddBackInStockSubscriberToGroupUseCase,
)

PROJECT_UUID = uuid4()
CONTACT_URN = "whatsapp:5511999887766"


class AddBackInStockSubscriberToGroupUseCaseTest(SimpleTestCase):
    def setUp(self):
        self.mock_flows = MagicMock()
        self.mock_ensure = MagicMock()
        self.use_case = AddBackInStockSubscriberToGroupUseCase(
            flows_service=self.mock_flows,
            ensure_group=self.mock_ensure,
        )

    def test_creates_contact_already_in_the_group(self):
        self.mock_flows.create_contact.return_value = {"uuid": "c1"}

        with self.assertLogs(
            "retail.webhooks.vtex.usecases.add_back_in_stock_subscriber_to_group",
            level="INFO",
        ) as logs:
            self.use_case.execute(PROJECT_UUID, "Maria Silva", "5511999887766")

        self.mock_ensure.execute.assert_called_once_with(PROJECT_UUID)
        self.mock_flows.create_contact.assert_called_once_with(
            project_uuid=str(PROJECT_UUID),
            name="Maria Silva",
            urns=[CONTACT_URN],
            groups=[BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME],
        )
        self.mock_flows.add_contact_to_group.assert_not_called()
        self.assertIn("Flows contact created in group", " ".join(logs.output))

    def test_adds_existing_urn_via_contact_actions(self):
        self.mock_flows.create_contact.side_effect = FlowsContactUrnAlreadyExistsError()
        self.mock_flows.add_contact_to_group.return_value = {}

        with self.assertLogs(
            "retail.webhooks.vtex.usecases.add_back_in_stock_subscriber_to_group",
            level="INFO",
        ) as logs:
            self.use_case.execute(PROJECT_UUID, "Maria Silva", "5511999887766")

        self.mock_flows.add_contact_to_group.assert_called_once_with(
            project_uuid=str(PROJECT_UUID),
            contacts=[CONTACT_URN],
            group=BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME,
        )
        self.assertIn("Existing Flows contact added to group", " ".join(logs.output))

    def test_warns_when_create_contact_fails(self):
        self.mock_flows.create_contact.return_value = None

        with self.assertLogs(
            "retail.webhooks.vtex.usecases.add_back_in_stock_subscriber_to_group",
            level="WARNING",
        ) as logs:
            self.use_case.execute(PROJECT_UUID, "Maria Silva", "5511999887766")

        self.mock_flows.add_contact_to_group.assert_not_called()
        self.assertIn("Flows contact was not created", " ".join(logs.output))

    def test_warns_when_add_existing_contact_fails(self):
        self.mock_flows.create_contact.side_effect = FlowsContactUrnAlreadyExistsError()
        self.mock_flows.add_contact_to_group.return_value = None

        with self.assertLogs(
            "retail.webhooks.vtex.usecases.add_back_in_stock_subscriber_to_group",
            level="WARNING",
        ) as logs:
            self.use_case.execute(PROJECT_UUID, "Maria Silva", "5511999887766")

        self.assertIn(
            "Existing Flows contact was not added to group", " ".join(logs.output)
        )

    def test_does_not_raise_when_ensure_group_blows_up(self):
        self.mock_ensure.execute.side_effect = RuntimeError("boom")

        with self.assertLogs(
            "retail.webhooks.vtex.usecases.add_back_in_stock_subscriber_to_group",
            level="ERROR",
        ) as logs:
            self.use_case.execute(PROJECT_UUID, "Maria Silva", "5511999887766")

        self.mock_flows.create_contact.assert_not_called()
        self.assertIn("Failed to add subscriber to Flows group", " ".join(logs.output))
