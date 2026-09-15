from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from retail.internal.test_mixins import patch_retail_auth
from retail.webhooks.vtex.usecases.dto import BackInStockStockChangeResult


ACCOUNT = "gaboulstore"
WEBHOOK_PATH = f"/webhook/vtex/back-in-stock/{ACCOUNT}/stock-change/"
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
        self.client = APIClient()
        self.use_case_patcher = patch(USE_CASE_PATH)
        self.mock_use_case_cls = self.use_case_patcher.start()
        self.mock_use_case_cls.return_value.execute.return_value = (
            BackInStockStockChangeResult(accepted=True)
        )
        self.addCleanup(self.use_case_patcher.stop)

    def tearDown(self):
        cache.clear()

    def test_url_matches_io_contract(self):
        self.assertEqual(
            reverse("back-in-stock-stock-change", args=[ACCOUNT]), WEBHOOK_PATH
        )

    def _post(self, payload, path_account=ACCOUNT):
        path = reverse("back-in-stock-stock-change", args=[path_account])
        return self.client.post(path, payload, format="json")

    def test_returns_401_without_token(self):
        response = self._post(VALID_PAYLOAD)

        self.assertIn(response.status_code, [401, 403])
        self.mock_use_case_cls.return_value.execute.assert_not_called()

    @patch_retail_auth(vtex_account=ACCOUNT)
    def test_accepted_true_uses_claim_account(self, _auth):
        response = self._post(VALID_PAYLOAD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"accepted": True})
        dto = self.mock_use_case_cls.return_value.execute.call_args[0][0]
        self.assertEqual(dto.account, ACCOUNT)
        self.assertEqual(dto.sku_id, "9")

    @patch_retail_auth(vtex_account=ACCOUNT)
    def test_uses_claim_account_not_path_account(self, _auth):
        response = self._post(VALID_PAYLOAD, path_account="americanas1224")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dto = self.mock_use_case_cls.return_value.execute.call_args[0][0]
        self.assertEqual(dto.account, ACCOUNT)

    @patch_retail_auth(vtex_account=ACCOUNT)
    def test_accepted_false_when_sku_not_waiting(self, _auth):
        self.mock_use_case_cls.return_value.execute.return_value = (
            BackInStockStockChangeResult(accepted=False, reason="sku_not_waiting")
        )

        response = self._post(VALID_PAYLOAD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data, {"accepted": False, "reason": "sku_not_waiting"}
        )
