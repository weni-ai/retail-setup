from unittest.mock import MagicMock

from django.test import TestCase

from retail.clients.exceptions import CustomAPIException
from retail.services.flows.service import (
    FlowsContactUrnAlreadyExistsError,
    FlowsService,
)


class TestFlowsService(TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.service = FlowsService(client=self.mock_client)
        self.user_email = "test@example.com"
        self.project_uuid = "project-uuid-123"
        self.payload = {"message": "test broadcast"}

    def test_init(self):
        service = FlowsService(client=self.mock_client)
        self.assertEqual(service.client, self.mock_client)

    def test_get_user_api_token_success(self):
        expected_response = {"token": "api-token-123", "expires_at": "2024-12-31"}
        self.mock_client.get_user_api_token.return_value = expected_response

        result = self.service.get_user_api_token(self.user_email, self.project_uuid)

        self.mock_client.get_user_api_token.assert_called_once_with(
            self.user_email, self.project_uuid
        )
        self.assertEqual(result, expected_response)

    def test_get_user_api_token_custom_api_exception(self):
        exception = CustomAPIException(status_code=404, detail="Not found")
        self.mock_client.get_user_api_token.side_effect = exception

        result = self.service.get_user_api_token(self.user_email, self.project_uuid)

        self.mock_client.get_user_api_token.assert_called_once_with(
            self.user_email, self.project_uuid
        )
        self.assertIsNone(result)

    def test_send_whatsapp_broadcast_success(self):
        # Mock successful response
        mock_response = {"status": 200, "message": "Broadcast sent successfully"}
        self.mock_client.send_whatsapp_broadcast.return_value = mock_response

        result = self.service.send_whatsapp_broadcast(self.payload)

        self.mock_client.send_whatsapp_broadcast.assert_called_once_with(
            payload=self.payload
        )
        self.assertEqual(result, mock_response)

    def test_send_whatsapp_broadcast_failure(self):
        # Mock failed response
        mock_response = {"status": 400, "error": "Bad request"}
        self.mock_client.send_whatsapp_broadcast.return_value = mock_response

        result = self.service.send_whatsapp_broadcast(self.payload)

        self.mock_client.send_whatsapp_broadcast.assert_called_once_with(
            payload=self.payload
        )
        self.assertEqual(result, mock_response)

    def test_send_whatsapp_broadcast_exception(self):
        # Mock exception
        exception = Exception("Network error")
        self.mock_client.send_whatsapp_broadcast.side_effect = exception

        with self.assertRaises(Exception):
            self.service.send_whatsapp_broadcast(self.payload)

        self.mock_client.send_whatsapp_broadcast.assert_called_once_with(
            payload=self.payload
        )

    def test_get_contact_groups_returns_payload(self):
        expected = {"results": [{"uuid": "g1", "name": "back-in-stock-subscribers"}]}
        self.mock_client.get_contact_groups.return_value = expected

        result = self.service.get_contact_groups(
            "proj-uuid", "back-in-stock-subscribers"
        )

        self.mock_client.get_contact_groups.assert_called_once_with(
            project_uuid="proj-uuid", name="back-in-stock-subscribers"
        )
        self.assertEqual(result, expected)

    def test_get_contact_groups_returns_none_on_client_error(self):
        self.mock_client.get_contact_groups.side_effect = CustomAPIException(
            status_code=500, detail="down"
        )

        result = self.service.get_contact_groups(
            "proj-uuid", "back-in-stock-subscribers"
        )

        self.assertIsNone(result)

    def test_get_contact_groups_returns_none_on_unexpected_error(self):
        self.mock_client.get_contact_groups.side_effect = RuntimeError("boom")

        result = self.service.get_contact_groups(
            "proj-uuid", "back-in-stock-subscribers"
        )

        self.assertIsNone(result)

    def test_create_contact_group_returns_payload(self):
        expected = {"uuid": "g1", "name": "back-in-stock-subscribers"}
        self.mock_client.create_contact_group.return_value = expected

        result = self.service.create_contact_group(
            "proj-uuid", "back-in-stock-subscribers"
        )

        self.mock_client.create_contact_group.assert_called_once_with(
            project_uuid="proj-uuid", name="back-in-stock-subscribers"
        )
        self.assertEqual(result, expected)

    def test_create_contact_group_returns_none_on_client_error(self):
        self.mock_client.create_contact_group.side_effect = CustomAPIException(
            status_code=400, detail="bad"
        )

        result = self.service.create_contact_group(
            "proj-uuid", "back-in-stock-subscribers"
        )

        self.assertIsNone(result)

    def test_create_contact_group_returns_none_on_unexpected_error(self):
        self.mock_client.create_contact_group.side_effect = RuntimeError("boom")

        result = self.service.create_contact_group(
            "proj-uuid", "back-in-stock-subscribers"
        )

        self.assertIsNone(result)

    def test_create_contact_returns_payload(self):
        expected = {"uuid": "c1"}
        self.mock_client.create_contact.return_value = expected

        result = self.service.create_contact(
            "proj-uuid",
            "Maria Silva",
            ["whatsapp:5511999887766"],
            ["back-in-stock-subscribers"],
        )

        self.mock_client.create_contact.assert_called_once_with(
            project_uuid="proj-uuid",
            name="Maria Silva",
            urns=["whatsapp:5511999887766"],
            groups=["back-in-stock-subscribers"],
        )
        self.assertEqual(result, expected)

    def test_create_contact_raises_when_urn_belongs_to_another_contact(self):
        self.mock_client.create_contact.side_effect = CustomAPIException(
            status_code=400,
            detail={"urns": ["URN belongs to another contact: uuid"]},
        )

        with self.assertRaises(FlowsContactUrnAlreadyExistsError):
            self.service.create_contact(
                "proj-uuid",
                "Maria Silva",
                ["whatsapp:5511999887766"],
                ["back-in-stock-subscribers"],
            )

    def test_create_contact_returns_none_on_other_client_error(self):
        self.mock_client.create_contact.side_effect = CustomAPIException(
            status_code=500, detail="down"
        )

        result = self.service.create_contact(
            "proj-uuid",
            "Maria Silva",
            ["whatsapp:5511999887766"],
            ["back-in-stock-subscribers"],
        )

        self.assertIsNone(result)

    def test_create_contact_returns_none_on_400_without_urn_conflict(self):
        self.mock_client.create_contact.side_effect = CustomAPIException(
            status_code=400, detail={"name": ["This field is required."]}
        )

        result = self.service.create_contact(
            "proj-uuid",
            "Maria Silva",
            ["whatsapp:5511999887766"],
            ["back-in-stock-subscribers"],
        )

        self.assertIsNone(result)

    def test_create_contact_returns_none_on_unexpected_error(self):
        self.mock_client.create_contact.side_effect = RuntimeError("boom")

        result = self.service.create_contact(
            "proj-uuid",
            "Maria Silva",
            ["whatsapp:5511999887766"],
            ["back-in-stock-subscribers"],
        )

        self.assertIsNone(result)

    def test_add_contact_to_group_returns_payload(self):
        self.mock_client.add_contact_to_group.return_value = {}

        result = self.service.add_contact_to_group(
            "proj-uuid",
            ["whatsapp:5511999887766"],
            "back-in-stock-subscribers",
        )

        self.mock_client.add_contact_to_group.assert_called_once_with(
            project_uuid="proj-uuid",
            contacts=["whatsapp:5511999887766"],
            group="back-in-stock-subscribers",
        )
        self.assertEqual(result, {})

    def test_add_contact_to_group_returns_none_on_client_error(self):
        self.mock_client.add_contact_to_group.side_effect = CustomAPIException(
            status_code=500, detail="down"
        )

        result = self.service.add_contact_to_group(
            "proj-uuid",
            ["whatsapp:5511999887766"],
            "back-in-stock-subscribers",
        )

        self.assertIsNone(result)

    def test_add_contact_to_group_returns_none_on_unexpected_error(self):
        self.mock_client.add_contact_to_group.side_effect = RuntimeError("boom")

        result = self.service.add_contact_to_group(
            "proj-uuid",
            ["whatsapp:5511999887766"],
            "back-in-stock-subscribers",
        )

        self.assertIsNone(result)
