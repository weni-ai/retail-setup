from unittest.mock import MagicMock

from django.test import TestCase

from retail.clients.exceptions import CustomAPIException
from retail.services.vtex_checkout.service import VtexCheckoutService


class VtexCheckoutServiceTest(TestCase):
    def setUp(self):
        self.mock_vtex_io = MagicMock()
        self.service = VtexCheckoutService(vtex_io_service=self.mock_vtex_io)
        self.account_domain = "test.myvtex.com"
        self.vtex_account = "test"

    def test_create_cart_delegates_with_force_new_cart(self):
        expected = {"orderFormId": "new-of"}
        self.mock_vtex_io.proxy_vtex.return_value = expected

        result = self.service.create_cart(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
        )

        self.assertEqual(result, expected)
        self.mock_vtex_io.proxy_vtex.assert_called_once_with(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            method="GET",
            path="/api/checkout/pub/orderForm",
            data=None,
            params={"forceNewCart": "true"},
        )

    def test_create_cart_appends_sales_channel(self):
        self.mock_vtex_io.proxy_vtex.return_value = {"orderFormId": "new-of"}

        self.service.create_cart(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            sales_channel="2",
        )

        params = self.mock_vtex_io.proxy_vtex.call_args.kwargs["params"]
        self.assertEqual(params["sc"], "2")

    def test_add_items_delegates_patch(self):
        order_items = [{"id": "1", "quantity": 1, "seller": "1"}]
        self.mock_vtex_io.proxy_vtex.return_value = {"items": order_items}

        result = self.service.add_items(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            order_form_id="of-1",
            order_items=order_items,
        )

        self.assertEqual(result, {"items": order_items})
        self.mock_vtex_io.proxy_vtex.assert_called_once_with(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            method="PATCH",
            path="/api/checkout/pub/orderForm/of-1/items",
            data={"orderItems": order_items},
            params=None,
        )

    def test_set_client_profile_data_delegates_post(self):
        profile = {"email": "a@b.com", "firstName": "Ada"}
        self.mock_vtex_io.proxy_vtex.return_value = {"clientProfileData": profile}

        result = self.service.set_client_profile_data(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            order_form_id="of-1",
            client_profile_data=profile,
        )

        self.assertEqual(result, {"clientProfileData": profile})
        path = self.mock_vtex_io.proxy_vtex.call_args.kwargs["path"]
        self.assertTrue(path.endswith("/attachments/clientProfileData"))

    def test_set_shipping_data_delegates_post(self):
        shipping = {"selectedAddresses": [{"postalCode": "01310-100"}]}
        self.mock_vtex_io.proxy_vtex.return_value = {"shippingData": shipping}

        result = self.service.set_shipping_data(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            order_form_id="of-1",
            shipping_data=shipping,
        )

        self.assertEqual(result, {"shippingData": shipping})
        path = self.mock_vtex_io.proxy_vtex.call_args.kwargs["path"]
        self.assertTrue(path.endswith("/attachments/shippingData"))

    def test_set_client_preferences_data_delegates_post(self):
        prefs = {"locale": "pt-BR", "optinNewsLetter": False}
        self.mock_vtex_io.proxy_vtex.return_value = {"clientPreferencesData": prefs}

        result = self.service.set_client_preferences_data(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            order_form_id="of-1",
            client_preferences_data=prefs,
        )

        self.assertEqual(result, {"clientPreferencesData": prefs})
        path = self.mock_vtex_io.proxy_vtex.call_args.kwargs["path"]
        self.assertTrue(path.endswith("/attachments/clientPreferencesData"))

    def test_set_marketing_data_delegates_post(self):
        marketing = {"utmCampaign": "summer"}
        self.mock_vtex_io.proxy_vtex.return_value = {"marketingData": marketing}

        result = self.service.set_marketing_data(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            order_form_id="of-1",
            marketing_data=marketing,
        )

        self.assertEqual(result, {"marketingData": marketing})
        path = self.mock_vtex_io.proxy_vtex.call_args.kwargs["path"]
        self.assertTrue(path.endswith("/attachments/marketingData"))

    def test_get_order_form_delegates_get(self):
        expected = {"orderFormId": "of-1", "items": []}
        self.mock_vtex_io.proxy_vtex.return_value = expected

        result = self.service.get_order_form(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            order_form_id="of-1",
        )

        self.assertEqual(result, expected)
        self.mock_vtex_io.proxy_vtex.assert_called_once_with(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            method="GET",
            path="/api/checkout/pub/orderForm/of-1",
            data=None,
            params=None,
        )

    def test_infra_error_returns_none(self):
        self.mock_vtex_io.proxy_vtex.side_effect = CustomAPIException(
            detail="boom", status_code=500
        )

        result = self.service.create_cart(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
        )

        self.assertIsNone(result)

    def test_unexpected_error_returns_none(self):
        self.mock_vtex_io.proxy_vtex.side_effect = RuntimeError("network")

        result = self.service.add_items(
            account_domain=self.account_domain,
            vtex_account=self.vtex_account,
            order_form_id="of-1",
            order_items=[{"id": "1", "quantity": 1, "seller": "1"}],
        )

        self.assertIsNone(result)
