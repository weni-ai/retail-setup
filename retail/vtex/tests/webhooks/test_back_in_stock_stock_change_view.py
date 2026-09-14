from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory

from retail.internal.test_mixins import patch_retail_auth
from retail.webhooks.vtex.usecases.dto import BackInStockStockChangeResult
from retail.webhooks.vtex.views.back_in_stock_stock_change import BackInStockStockChange


WEBHOOK_PATH = "/webhook/vtex/back-in-stock/api/stock-change/"
USE_CASE_PATH = (
    "retail.webhooks.vtex.views.back_in_stock_stock_change."
    "HandleBackInStockStockChangeUseCase"
)

VALID_PAYLOAD = {
    "sku_id": "9",
    "account": "body-must-not-win",
    "is_active": True,
    "stock_modified": True,
}


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "back-in-stock-stock-change-view-tests",
        }
    }
)
class BackInStockStockChangeViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()
        self.view = BackInStockStockChange.as_view()
        self.use_case_patcher = patch(USE_CASE_PATH)
        self.mock_use_case_cls = self.use_case_patcher.start()
        self.addCleanup(self.use_case_patcher.stop)

    def tearDown(self):
        cache.clear()

    def test_url_matches_io_contract(self):
        self.assertEqual(reverse("back-in-stock-stock-change"), WEBHOOK_PATH)

    def _post(self, payload):
        request = self.factory.post(WEBHOOK_PATH, payload, format="json")
        return self.view(request)

    def test_returns_401_without_token(self):
        response = self._post(VALID_PAYLOAD)

        self.assertIn(response.status_code, [401, 403])
        self.mock_use_case_cls.return_value.execute.assert_not_called()

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_accepted_true_uses_claim_account(self, _auth):
        self.mock_use_case_cls.return_value.execute.return_value = (
            BackInStockStockChangeResult(accepted=True)
        )

        response = self._post(VALID_PAYLOAD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"accepted": True})
        dto = self.mock_use_case_cls.return_value.execute.call_args[0][0]
        self.assertEqual(dto.account, "gaboulstore")
        self.assertEqual(dto.sku_id, "9")

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_accepted_false_when_sku_not_waiting(self, _auth):
        self.mock_use_case_cls.return_value.execute.return_value = (
            BackInStockStockChangeResult(accepted=False, reason="sku_not_waiting")
        )

        response = self._post(VALID_PAYLOAD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data, {"accepted": False, "reason": "sku_not_waiting"}
        )
