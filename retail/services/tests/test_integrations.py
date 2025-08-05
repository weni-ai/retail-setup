from unittest.mock import MagicMock, patch
from datetime import datetime

from django.test import TestCase

from retail.clients.exceptions import CustomAPIException
from retail.services.integrations.service import IntegrationsService


class TestIntegrationsService(TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.service = IntegrationsService(client=self.mock_client)
        self.project_uuid = "project-uuid-123"
        self.app_uuid = "app-uuid-123"
        self.domain = "example.com"
        self.store = "store.example.com"

    def test_init_with_client(self):
        service = IntegrationsService(client=self.mock_client)
        self.assertEqual(service.client, self.mock_client)

    @patch("retail.services.integrations.service.IntegrationsClient")
    def test_init_without_client(self, mock_integrations_client):
        IntegrationsService()
        mock_integrations_client.assert_called_once()

    def test_get_vtex_integration_detail_success(self):
        expected_response = {"integration_id": "123", "status": "active"}
        self.mock_client.get_vtex_integration_detail.return_value = expected_response

        result = self.service.get_vtex_integration_detail(self.project_uuid)

        self.mock_client.get_vtex_integration_detail.assert_called_once_with(
            self.project_uuid
        )
        self.assertEqual(result, expected_response)

    def test_get_vtex_integration_detail_custom_api_exception(self):
        exception = CustomAPIException(status_code=404, detail="Not found")
        self.mock_client.get_vtex_integration_detail.side_effect = exception

        result = self.service.get_vtex_integration_detail(self.project_uuid)

        self.mock_client.get_vtex_integration_detail.assert_called_once_with(
            self.project_uuid
        )
        self.assertIsNone(result)

    @patch("retail.services.integrations.service.datetime")
    def test_create_abandoned_cart_template_success(self, mock_datetime):
        mock_now = datetime(2024, 1, 15, 10, 30, 45)
        mock_datetime.now.return_value = mock_now
        template_uuid = "template-uuid-123"
        self.mock_client.create_template_message.return_value = template_uuid

        result = self.service.create_abandoned_cart_template(
            self.app_uuid, self.project_uuid, self.domain
        )

        expected_template_name = "weni_abandoned_cart_20240115103045"
        self.mock_client.create_template_message.assert_called_once_with(
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            name=expected_template_name,
            category="MARKETING",
        )
        self.assertEqual(self.mock_client.create_template_translation.call_count, 3)
        self.assertEqual(result, expected_template_name)

    @patch("retail.services.integrations.service.datetime")
    def test_create_abandoned_cart_template_custom_api_exception(self, mock_datetime):
        mock_now = datetime(2024, 1, 15, 10, 30, 45)
        mock_datetime.now.return_value = mock_now
        exception = CustomAPIException(status_code=400, detail="Bad request")
        self.mock_client.create_template_message.side_effect = exception

        with self.assertRaises(CustomAPIException):
            self.service.create_abandoned_cart_template(
                self.app_uuid, self.project_uuid, self.domain
            )

    @patch("retail.services.integrations.service.datetime")
    def test_create_order_status_templates_success(self, mock_datetime):
        mock_now = datetime(2024, 1, 15, 10, 30, 45)
        mock_datetime.now.return_value = mock_now

        result = self.service.create_order_status_templates(
            self.app_uuid, self.project_uuid, self.store
        )

        self.mock_client.create_library_template_message.assert_called_once()
        call_args = self.mock_client.create_library_template_message.call_args

        self.assertEqual(call_args[1]["app_uuid"], self.app_uuid)
        self.assertEqual(call_args[1]["project_uuid"], self.project_uuid)
        self.assertIn("library_templates", call_args[1]["template_data"])
        self.assertIn("languages", call_args[1]["template_data"])
        self.assertEqual(
            call_args[1]["template_data"]["languages"], ["pt_BR", "en", "es"]
        )

        expected_keys = [
            "invoiced",
            "payment-approved",
            "order-created",
            "canceled",
            "invoice-no-file",
        ]
        for key in expected_keys:
            self.assertIn(key, result)

    def test_get_synchronized_templates_all_synchronized(self):
        template_list = ["template1", "template2"]
        templates = {
            "template1": [{"status": "APPROVED"}, {"status": "APPROVED"}],
            "template2": [{"status": "APPROVED"}],
        }
        self.mock_client.get_synchronized_templates.return_value = templates

        result = self.service.get_synchronized_templates(self.app_uuid, template_list)

        self.mock_client.get_synchronized_templates.assert_called_once_with(
            self.app_uuid
        )
        self.assertEqual(result, "synchronized")

    def test_get_synchronized_templates_no_templates(self):
        template_list = ["template1", "template2"]
        self.mock_client.get_synchronized_templates.return_value = {}

        result = self.service.get_synchronized_templates(self.app_uuid, template_list)

        self.assertEqual(result, "pending")

    def test_get_synchronized_templates_missing_template(self):
        template_list = ["template1", "template2"]
        templates = {"template1": [{"status": "APPROVED"}]}
        self.mock_client.get_synchronized_templates.return_value = templates

        result = self.service.get_synchronized_templates(self.app_uuid, template_list)

        self.assertEqual(result, "pending")

    def test_get_synchronized_templates_rejected_status(self):
        template_list = ["template1", "template2"]
        templates = {
            "template1": [{"status": "REJECTED"}],
            "template2": [{"status": "APPROVED"}],
        }
        self.mock_client.get_synchronized_templates.return_value = templates

        result = self.service.get_synchronized_templates(self.app_uuid, template_list)

        self.assertEqual(result, "rejected")

    def test_get_synchronized_templates_pending_status(self):
        template_list = ["template1", "template2"]
        templates = {
            "template1": [{"status": "PENDING"}],
            "template2": [{"status": "APPROVED"}],
        }
        self.mock_client.get_synchronized_templates.return_value = templates

        result = self.service.get_synchronized_templates(self.app_uuid, template_list)

        self.assertEqual(result, "pending")

    def test_create_template(self):
        template_uuid = "template-uuid-123"
        name = "test_template"
        category = "MARKETING"
        self.mock_client.create_template_message.return_value = template_uuid

        result = self.service.create_template(
            self.app_uuid, self.project_uuid, name, category
        )

        self.mock_client.create_template_message.assert_called_once_with(
            self.app_uuid, self.project_uuid, name, category, gallery_version=None
        )
        self.assertEqual(result, template_uuid)

    def test_create_template_with_gallery_version(self):
        template_uuid = "template-uuid-123"
        name = "test_template"
        category = "MARKETING"
        gallery_version = "v1.0"
        self.mock_client.create_template_message.return_value = template_uuid

        result = self.service.create_template(
            self.app_uuid, self.project_uuid, name, category, gallery_version
        )

        self.mock_client.create_template_message.assert_called_once_with(
            self.app_uuid,
            self.project_uuid,
            name,
            category,
            gallery_version=gallery_version,
        )
        self.assertEqual(result, template_uuid)

    def test_create_template_translation(self):
        template_uuid = "template-uuid-123"
        payload = {"language": "pt_BR", "body": {"text": "Test message"}}
        expected_response = {"translation_id": "trans-123"}
        self.mock_client.create_template_translation.return_value = expected_response

        result = self.service.create_template_translation(
            self.app_uuid, self.project_uuid, template_uuid, payload
        )

        self.mock_client.create_template_translation.assert_called_once_with(
            self.app_uuid, self.project_uuid, template_uuid, payload
        )
        self.assertEqual(result, expected_response)

    def test_create_library_template(self):
        template_data = {"library_templates": [], "languages": ["pt_BR"]}
        template_uuid = "library-template-uuid-123"
        self.mock_client.create_library_template.return_value = template_uuid

        result = self.service.create_library_template(
            self.app_uuid, self.project_uuid, template_data
        )

        self.mock_client.create_library_template.assert_called_once_with(
            self.app_uuid, self.project_uuid, template_data
        )
        self.assertEqual(result, template_uuid)

    def test_fetch_template_metrics_success(self):
        template_versions = ["v1", "v2"]
        start = "2024-01-01"
        end = "2024-01-31"
        expected_response = {"v1": {"sent": 10}, "v2": {"sent": 5}}
        self.mock_client.fetch_template_metrics.return_value = expected_response

        result = self.service.fetch_template_metrics(
            self.app_uuid, template_versions, start, end
        )

        self.mock_client.fetch_template_metrics.assert_called_once_with(
            self.app_uuid, template_versions, start, end
        )
        self.assertEqual(result, expected_response)

    def test_fetch_templates_from_user_with_approved_translations(self):
        templates_data = [
            {
                "name": "template1",
                "category": "UTILITY",
                "translations": [
                    {
                        "language": "en",
                        "status": "APPROVED",
                        "header": None,
                        "body": {"type": "BODY", "text": "Hi"},
                        "footer": None,
                        "buttons": [{"button_type": "URL", "url": "someurl"}],
                        "body_params": ["test"],
                    },
                    {
                        "language": "es",
                        "status": "APPROVED",
                        "header": None,
                        "body": {"type": "BODY", "text": "Hola"},
                        "footer": None,
                        "buttons": [],
                    },
                ],
            },
            {
                "name": "template2",
                "category": "MARKETING",
                "translations": [
                    {
                        "language": "en",
                        "status": "PENDING",
                        "body": {"type": "BODY", "text": "Pending"},
                        "buttons": [],
                    }
                ],
            },
        ]
        self.mock_client.fetch_templates_from_user.return_value = templates_data
        template_names = ["template1", "template2"]
        language = "en"
        result = self.service.fetch_templates_from_user(
            self.app_uuid, self.project_uuid, template_names, language
        )

        self.mock_client.fetch_templates_from_user.assert_called_once_with(
            self.app_uuid, self.project_uuid
        )
        self.assertIn("template1", result)
        self.assertEqual(result["template1"]["body"], {"type": "BODY", "text": "Hi"})
        self.assertNotIn("template2", result)

    def test_fetch_templates_from_user_no_approved_translation(self):
        templates_data = [
            {
                "name": "template1",
                "category": "UTILITY",
                "translations": [{"language": "en", "status": "REJECTED"}],
            },
        ]
        self.mock_client.fetch_templates_from_user.return_value = templates_data
        result = self.service.fetch_templates_from_user(
            self.app_uuid, self.project_uuid, ["template1"], "en"
        )
        self.assertEqual(result, {})

    def test_create_order_status_templates_with_exception(self):
        self.mock_client.create_library_template_message.side_effect = (
            CustomAPIException(status_code=400, detail="error")
        )
        with patch("retail.services.integrations.service.datetime") as mock_datetime:
            mock_now = datetime(2024, 1, 15, 10, 30, 45)
            mock_datetime.now.return_value = mock_now

            with self.assertRaises(CustomAPIException):
                self.service.create_order_status_templates(
                    self.app_uuid, self.project_uuid, self.store
                )

    def test_create_template_translation_exception(self):
        self.mock_client.create_template_translation.side_effect = CustomAPIException(
            status_code=400, detail="error"
        )
        with self.assertRaises(CustomAPIException):
            self.service.create_template_translation(
                self.app_uuid, self.project_uuid, "template-uuid", {"language": "pt_BR"}
            )

    def test_create_library_template_exception(self):
        self.mock_client.create_library_template.side_effect = CustomAPIException(
            status_code=400, detail="error"
        )
        with self.assertRaises(CustomAPIException):
            self.service.create_library_template(
                self.app_uuid,
                self.project_uuid,
                {"library_templates": [], "languages": ["pt_BR"]},
            )
