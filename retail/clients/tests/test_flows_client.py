from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from retail.clients.flows.client import FlowsClient


@override_settings(FLOWS_REST_ENDPOINT="http://test-flows.local")
class FlowsClientContactGroupTest(SimpleTestCase):
    def setUp(self):
        jwt_usecase = MagicMock()
        jwt_usecase.generate_jwt_token.return_value = "module-jwt"
        self.client = FlowsClient(jwt_usecase=jwt_usecase)

    @patch.object(FlowsClient, "make_request")
    def test_get_contact_groups_uses_v2_route(self, mock_make_request):
        response = MagicMock()
        response.json.return_value = {"results": []}
        mock_make_request.return_value = response

        result = self.client.get_contact_groups(
            project_uuid="proj-uuid", name="back-in-stock-subscribers"
        )

        mock_make_request.assert_called_once_with(
            "http://test-flows.local/api/v2/groups.json",
            method="GET",
            params={"project": "proj-uuid", "name": "back-in-stock-subscribers"},
            headers={
                "Authorization": "Bearer module-jwt",
                "Content-Type": "application/json",
            },
        )
        self.client.jwt_usecase.generate_jwt_token.assert_called_once_with("proj-uuid")
        self.assertEqual(result, {"results": []})

    @patch.object(FlowsClient, "make_request")
    def test_create_contact_group_posts_name(self, mock_make_request):
        response = MagicMock()
        response.json.return_value = {
            "uuid": "group-uuid",
            "name": "back-in-stock-subscribers",
        }
        mock_make_request.return_value = response

        result = self.client.create_contact_group(
            project_uuid="proj-uuid", name="back-in-stock-subscribers"
        )

        mock_make_request.assert_called_once_with(
            "http://test-flows.local/api/v2/groups.json",
            method="POST",
            params={"project": "proj-uuid"},
            json={"name": "back-in-stock-subscribers"},
            headers={
                "Authorization": "Bearer module-jwt",
                "Content-Type": "application/json",
            },
        )
        self.client.jwt_usecase.generate_jwt_token.assert_called_once_with("proj-uuid")
        self.assertEqual(result["uuid"], "group-uuid")
