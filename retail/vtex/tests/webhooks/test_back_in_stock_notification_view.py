from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory

from retail.internal.test_mixins import patch_retail_auth
from retail.webhooks.vtex.usecases.dto import (
    EnqueueBackInStockNotificationsDTO,
    ProcessBackInStockNotificationDTO,
)
from retail.webhooks.vtex.views.back_in_stock_notification import (
    NOTIFICATION_RECEIVED,
    BackInStockNotification,
)


WEBHOOK_PATH = "/webhook/vtex/back-in-stock/api/notification/"
USE_CASE_PATH = (
    "retail.webhooks.vtex.views.back_in_stock_notification."
    "EnqueueBackInStockNotificationsUseCase"
)

CACHE_SETTINGS = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "back-in-stock-notification-view-tests",
    }
}

VALID_PAYLOAD = {
    "sku_id": "9",
    "shoppers": [
        {
            "phone": "5511999887766",
            "name": "Maria Silva",
            "locale": "pt-BR",
        },
        {
            "phone": "5511888776655",
            "name": "João Santos",
        },
    ],
}


@override_settings(
    CACHES=CACHE_SETTINGS,
    BACK_IN_STOCK_CELERY_QUEUE="back-in-stock",
)
class BackInStockNotificationViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()
        self.view = BackInStockNotification.as_view()
        self.use_case_patcher = patch(USE_CASE_PATH)
        self.mock_use_case_cls = self.use_case_patcher.start()
        self.addCleanup(self.use_case_patcher.stop)

    def tearDown(self):
        cache.clear()

    def test_url_matches_io_contract(self):
        self.assertEqual(reverse("back-in-stock"), WEBHOOK_PATH)

    def _post(self, payload):
        request = self.factory.post(WEBHOOK_PATH, payload, format="json")
        return self.view(request)

    def test_returns_401_without_token(self):
        response = self._post(VALID_PAYLOAD)

        self.assertIn(response.status_code, [401, 403])
        self.mock_use_case_cls.return_value.execute.assert_not_called()

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_returns_400_when_sku_id_missing(self, _auth):
        payload = {**VALID_PAYLOAD}
        del payload["sku_id"]

        response = self._post(payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mock_use_case_cls.return_value.execute.assert_not_called()

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_returns_400_when_shoppers_missing(self, _auth):
        payload = {"sku_id": "9"}

        response = self._post(payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mock_use_case_cls.return_value.execute.assert_not_called()

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_returns_400_when_shoppers_is_empty(self, _auth):
        payload = {"sku_id": "9", "shoppers": []}

        response = self._post(payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mock_use_case_cls.return_value.execute.assert_not_called()

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_returns_400_when_a_shopper_phone_is_missing(self, _auth):
        payload = {
            "sku_id": "9",
            "shoppers": [{"name": "Maria Silva"}],
        }

        response = self._post(payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mock_use_case_cls.return_value.execute.assert_not_called()

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_returns_400_when_a_shopper_phone_is_not_digits_only(self, _auth):
        payload = {
            "sku_id": "9",
            "shoppers": [{"phone": "+55 11 99988-7766"}],
        }

        response = self._post(payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mock_use_case_cls.return_value.execute.assert_not_called()

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_rejects_legacy_single_shopper_payload(self, _auth):
        payload = {
            "sku_id": "9",
            "phone": "5511999887766",
            "name": "Maria Silva",
            "locale": "pt-BR",
        }

        response = self._post(payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.mock_use_case_cls.return_value.execute.assert_not_called()

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_delegates_validated_batch_to_use_case(self, _auth):
        response = self._post(VALID_PAYLOAD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], NOTIFICATION_RECEIVED)
        self.assertNotIn("discarded", response.data)
        self.mock_use_case_cls.return_value.execute.assert_called_once_with(
            EnqueueBackInStockNotificationsDTO(
                account="gaboulstore",
                shoppers=(
                    ProcessBackInStockNotificationDTO(
                        sku_id="9",
                        phone="5511999887766",
                        name="Maria Silva",
                        locale="pt-BR",
                    ),
                    ProcessBackInStockNotificationDTO(
                        sku_id="9",
                        phone="5511888776655",
                        name="João Santos",
                        locale="pt-BR",
                    ),
                ),
            )
        )

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_ignores_account_and_project_id_in_body(self, _auth):
        payload = {
            **VALID_PAYLOAD,
            "account": "otherstore",
            "project_id": "11111111-1111-1111-1111-111111111111",
        }

        response = self._post(payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dto = self.mock_use_case_cls.return_value.execute.call_args.args[0]
        self.assertEqual(dto.account, "gaboulstore")

    @patch_retail_auth(vtex_account="gaboulstore")
    def test_optional_shopper_fields_are_not_required(self, _auth):
        payload = {
            "sku_id": "9",
            "shoppers": [{"phone": "5511999887766"}],
        }

        response = self._post(payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dto = self.mock_use_case_cls.return_value.execute.call_args.args[0]
        self.assertEqual(len(dto.shoppers), 1)
        self.assertEqual(dto.shoppers[0].name, "")
        self.assertEqual(dto.shoppers[0].locale, "pt-BR")
