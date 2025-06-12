from unittest.mock import MagicMock
from django.test import TestCase

from retail.services.vtex.service import VtexService


class TestVtexService(TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.service = VtexService(client=self.mock_client)
        self.account_domain = "test-account.vtexcommercestable.com.br"
        self.order_form_id = "order-form-123"
        self.utm_source = "google"

    def test_init_with_client(self):
        service = VtexService(client=self.mock_client)
        self.assertEqual(service.client, self.mock_client)

    def test_set_order_form_marketing_data_success(self):
        expected_response = {
            "orderFormId": self.order_form_id,
            "marketingData": {"utmSource": self.utm_source},
            "status": "success",
        }
        self.mock_client.set_order_form_marketing_data.return_value = expected_response

        result = self.service.set_order_form_marketing_data(
            self.account_domain, self.order_form_id, self.utm_source
        )

        self.mock_client.set_order_form_marketing_data.assert_called_once_with(
            self.account_domain, self.order_form_id, self.utm_source
        )
        self.assertEqual(result, expected_response)
