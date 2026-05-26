from unittest.mock import MagicMock, patch
from django.test import TestCase

from retail.clients.exceptions import CustomAPIException
from retail.services.meta.service import MetaService


class TestMetaService(TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.service = MetaService(client=self.mock_client)
        self.template_name = "test_template"
        self.language = "pt_BR"

    def test_init_with_client(self):
        service = MetaService(client=self.mock_client)
        self.assertEqual(service.client, self.mock_client)

    @patch("retail.services.meta.service.MetaClient")
    def test_init_without_client(self, mock_meta_client):
        MetaService()
        mock_meta_client.assert_called_once()

    def test_get_pre_approved_template_success(self):
        expected_response = {
            "template_id": "123",
            "name": self.template_name,
            "language": self.language,
            "status": "approved",
        }
        self.mock_client.get_pre_approved_template.return_value = expected_response

        result = self.service.get_pre_approved_template(
            self.template_name, self.language
        )

        self.mock_client.get_pre_approved_template.assert_called_once_with(
            self.template_name, self.language
        )
        self.assertEqual(result, expected_response)

    def test_create_flow_delegates_to_client(self):
        expected = {"id": "flow-1"}
        self.mock_client.create_flow.return_value = expected
        flow_json = {"version": "7.3"}

        result = self.service.create_flow(
            waba_id="waba-1",
            name="flow_x",
            categories=["SHOPPING"],
            endpoint_uri="https://example.com/hook",
            flow_json=flow_json,
        )

        self.mock_client.create_flow.assert_called_once_with(
            waba_id="waba-1",
            name="flow_x",
            categories=["SHOPPING"],
            endpoint_uri="https://example.com/hook",
            flow_json=flow_json,
        )
        self.assertEqual(result, expected)

    def test_register_public_key_delegates_to_client(self):
        expected = {"success": True}
        self.mock_client.register_public_key.return_value = expected

        result = self.service.register_public_key(
            phone_number_id="phone-1", public_key_pem="-----PUB-----"
        )

        self.mock_client.register_public_key.assert_called_once_with(
            "phone-1", "-----PUB-----"
        )
        self.assertEqual(result, expected)

    def test_publish_flow_delegates_to_client(self):
        expected = {"success": True}
        self.mock_client.publish_flow.return_value = expected

        result = self.service.publish_flow("flow-123")

        self.mock_client.publish_flow.assert_called_once_with("flow-123")
        self.assertEqual(result, expected)

    def test_submit_template_sample_delegates_to_client_and_returns_body(self):
        sample_body = {"type": "text", "text": {"body": "Hello"}}
        expected = {"success": True, "category": "UTILITY"}
        self.mock_client.submit_template_sample.return_value = expected

        result = self.service.submit_template_sample("waba-1", sample_body)

        self.mock_client.submit_template_sample.assert_called_once_with(
            "waba-1", sample_body
        )
        self.assertEqual(result, expected)

    def test_submit_template_sample_propagates_custom_api_exception(self):
        sample_body = {"type": "text", "text": {"body": "Hello"}}
        upstream_exc = CustomAPIException(
            detail={"error": {"code": 2388341}}, status_code=403
        )
        self.mock_client.submit_template_sample.side_effect = upstream_exc

        with self.assertRaises(CustomAPIException) as ctx:
            self.service.submit_template_sample("waba-1", sample_body)

        self.assertIs(ctx.exception, upstream_exc)

    def test_submit_template_sample_propagates_unexpected_exception(self):
        sample_body = {"type": "text", "text": {"body": "Hello"}}
        upstream_exc = RuntimeError("connection reset")
        self.mock_client.submit_template_sample.side_effect = upstream_exc

        with self.assertRaises(RuntimeError) as ctx:
            self.service.submit_template_sample("waba-1", sample_body)

        self.assertIs(ctx.exception, upstream_exc)
