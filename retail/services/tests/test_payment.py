from unittest.mock import MagicMock, patch

from django.test import TestCase

from retail.clients.exceptions import CustomAPIException
from retail.services.payment.service import PaymentService


class TestPaymentService(TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.service = PaymentService(client=self.mock_client)
        self.kwargs = {
            "channel_uuid": "ch-1",
            "private_key_pem": "-----PRIV-----",
            "phone_number": "5511999999999",
            "project_uuid": "proj-1",
            "phone_number_id": "phone-1",
            "waba_id": "waba-1",
        }

    def test_init_with_client(self):
        service = PaymentService(client=self.mock_client)
        self.assertEqual(service.client, self.mock_client)

    @patch("retail.services.payment.service.PaymentClient")
    def test_init_without_client(self, mock_payment_client):
        PaymentService()
        mock_payment_client.assert_called_once()

    def test_update_channel_success(self):
        expected = {"status": "ok"}
        self.mock_client.update_channel.return_value = expected

        result = self.service.update_channel(**self.kwargs)

        self.mock_client.update_channel.assert_called_once_with(**self.kwargs)
        self.assertEqual(result, expected)

    def test_update_channel_returns_none_on_api_exception(self):
        self.mock_client.update_channel.side_effect = CustomAPIException(
            status_code=502, detail="bad gateway"
        )

        result = self.service.update_channel(**self.kwargs)

        self.assertIsNone(result)
