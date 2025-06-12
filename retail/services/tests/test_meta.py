from unittest.mock import MagicMock, patch
from django.test import TestCase

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
