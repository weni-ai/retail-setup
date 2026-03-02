from unittest.mock import MagicMock
from django.test import TestCase

from retail.services.vtex_io.service import VtexIOService


class TestVtexIOService(TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.service = VtexIOService(client=self.mock_client)
        self.account_domain = "test-account.vtexcommercestable.com.br"
        self.vtex_account = "test-account"
        self.order_form_id = "order-form-123"
        self.user_email = "test@example.com"
        self.order_id = "order-123"
        self.query_params = "status=ready-for-handling"

    def test_init_with_client(self):
        service = VtexIOService(client=self.mock_client)
        self.assertEqual(service.client, self.mock_client)

    def test_init_without_client(self):
        service = VtexIOService()
        self.assertIsNotNone(service.client)

    def test_get_order_form_details_success(self):
        expected_response = {
            "orderFormId": self.order_form_id,
            "items": [],
            "totalizers": [],
            "clientProfileData": {},
        }
        self.mock_client.get_order_form_details.return_value = expected_response

        result = self.service.get_order_form_details(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            order_form_id=self.order_form_id,
        )

        self.mock_client.get_order_form_details.assert_called_once_with(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            order_form_id=self.order_form_id,
        )
        self.assertEqual(result, expected_response)

    def test_get_order_details_success(self):
        expected_response = {
            "orders": [
                {
                    "orderId": "order-123",
                    "status": "ready-for-handling",
                    "clientProfileData": {"email": self.user_email},
                }
            ]
        }
        self.mock_client.get_order_details.return_value = expected_response

        result = self.service.get_order_details(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            user_email=self.user_email,
        )

        self.mock_client.get_order_details.assert_called_once_with(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            user_email=self.user_email,
        )
        self.assertEqual(result, expected_response)

    def test_get_order_details_by_id_success(self):
        expected_response = {
            "orderId": self.order_id,
            "status": "ready-for-handling",
            "items": [],
            "totalizers": [],
        }
        self.mock_client.get_order_details_by_id.return_value = expected_response

        result = self.service.get_order_details_by_id(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            order_id=self.order_id,
        )

        self.mock_client.get_order_details_by_id.assert_called_once_with(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            order_id=self.order_id,
        )
        self.assertEqual(result, expected_response)

    def test_get_orders_success(self):
        expected_response = {
            "list": [
                {"orderId": "order-123", "status": "ready-for-handling"},
                {"orderId": "order-456", "status": "invoiced"},
            ],
            "paging": {"total": 2, "pages": 1},
        }
        self.mock_client.get_orders.return_value = expected_response

        result = self.service.get_orders(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            query_params=self.query_params,
        )

        self.mock_client.get_orders.assert_called_once_with(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            query_params=self.query_params,
        )
        self.assertEqual(result, expected_response)

    def test_get_account_identifier_success(self):
        expected_response = {
            "id": "account-123",
            "name": "Test Account",
            "accountName": "testaccount",
        }
        self.mock_client.get_account_identifier.return_value = expected_response

        result = self.service.get_account_identifier(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
        )

        self.mock_client.get_account_identifier.assert_called_once_with(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
        )
        self.assertEqual(result, expected_response)
