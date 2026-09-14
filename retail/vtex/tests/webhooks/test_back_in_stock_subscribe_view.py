from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory

from retail.internal.test_mixins import patch_retail_auth
from retail.webhooks.vtex.usecases.exceptions import ProjectNotFoundError
from retail.webhooks.vtex.views.back_in_stock_subscribe import BackInStockSubscribe


WEBHOOK_PATH = "/webhook/vtex/back-in-stock/api/subscribe/"
USE_CASE_PATH = (
    "retail.webhooks.vtex.views.back_in_stock_subscribe.SubscribeBackInStockUseCase"
)

VALID_PAYLOAD = {
    "sku_id": "9",
    "phone": "5511999887766",
    "name": "Maria Silva",
    "account": "body-must-not-win",
    "seller": "1",
    "sales_channel": "1",
    "locale": "pt-BR",
}


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "back-in-stock-subscribe-view-tests",
        }
    }
)
class BackInStockSubscribeViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()
        self.view = BackInStockSubscribe.as_view()
        self.use_case_patcher = patch(USE_CASE_PATH)
        self.mock_use_case_cls = self.use_case_patcher.start()
        self.addCleanup(self.use_case_patcher.stop)

    def tearDown(self):
        cache.clear()

    def test_url_matches_io_contract(self):
        self.assertEqual(reverse("back-in-stock-subscribe"), WEBHOOK_PATH)

    def _post(self, payload):
        request = self.factory.post(WEBHOOK_PATH, payload, format="json")
        return self.view(request)

    def test_returns_401_without_token(self):
        response = self._post(VALID_PAYLOAD)

        self.assertIn(response.status_code, [401, 403])
        self.mock_use_case_cls.return_value.execute.assert_not_called()

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_uses_claim_account_not_body_account(self, _auth):
        response = self._post(VALID_PAYLOAD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dto = self.mock_use_case_cls.return_value.execute.call_args[0][0]
        self.assertEqual(dto.account, "gaboulstore")
        self.assertEqual(dto.sku_id, "9")
        self.assertEqual(dto.seller, "1")
        self.assertEqual(response.data, {"accepted": True})

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_returns_400_when_phone_has_non_digits(self, _auth):
        payload = {**VALID_PAYLOAD, "phone": "+55 11 99988-7766"}

        response = self._post(payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mock_use_case_cls.return_value.execute.assert_not_called()

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_returns_404_when_project_missing(self, _auth):
        self.mock_use_case_cls.return_value.execute.side_effect = ProjectNotFoundError()

        response = self._post(VALID_PAYLOAD)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
