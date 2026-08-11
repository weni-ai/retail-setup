from unittest.mock import MagicMock

from django.test import TestCase

from retail.vtex.usecases.clone_order_form import (
    ClonedOrderFormDTO,
    CloneOrderFormUseCase,
)


def _full_source_order_form(**overrides):
    base = {
        "orderFormId": "source-of",
        "salesChannel": "1",
        "items": [
            {"id": "sku-1", "quantity": 2, "seller": "1", "price": 1000},
            {"id": "sku-2", "quantity": 1, "seller": "1", "price": 500},
        ],
        "clientProfileData": {
            "email": "buyer@example.com",
            "firstName": "Ada",
            "lastName": "Lovelace",
            "document": "123",
            "documentType": "cpf",
            "phone": "+5511999999999",
            "isCorporate": False,
        },
        "shippingData": {
            "selectedAddresses": [{"postalCode": "01310-100"}],
            "logisticsInfo": [
                {
                    "itemIndex": 0,
                    "selectedSla": "Normal",
                    "selectedDeliveryChannel": "delivery",
                }
            ],
        },
        "clientPreferencesData": {"locale": "pt-BR", "optinNewsLetter": True},
        "marketingData": {
            "utmCampaign": "summer",
            "coupon": "SAVE10",
            "marketingTags": ["vip"],
        },
    }
    base.update(overrides)
    return base


class CloneOrderFormUseCaseTest(TestCase):
    def setUp(self):
        self.mock_checkout = MagicMock()
        self.use_case = CloneOrderFormUseCase(checkout_service=self.mock_checkout)
        self.project_uuid = "11111111-1111-1111-1111-111111111111"
        self.vtex_account = "test-account"

        self.use_case._get_vtex_context = MagicMock(
            return_value=(self.vtex_account, "test-account.myvtex.com")
        )

        self.mock_checkout.create_cart.return_value = {"orderFormId": "clone-of"}
        self.mock_checkout.add_items.return_value = {"orderFormId": "clone-of"}
        self.mock_checkout.set_client_profile_data.return_value = {}
        self.mock_checkout.set_shipping_data.return_value = {}
        self.mock_checkout.set_client_preferences_data.return_value = {}
        self.mock_checkout.set_marketing_data.return_value = {}

    def test_execute_full_clone_success(self):
        source = _full_source_order_form()

        result = self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=source,
        )

        self.assertIsInstance(result, ClonedOrderFormDTO)
        self.assertEqual(result.order_form_id, "clone-of")
        self.assertEqual(result.marketing_data["utmCampaign"], "summer")
        self.mock_checkout.create_cart.assert_called_once_with(
            account_domain="test-account.myvtex.com",
            vtex_account=self.vtex_account,
            sales_channel="1",
        )
        add_kwargs = self.mock_checkout.add_items.call_args.kwargs
        self.assertEqual(
            add_kwargs["order_items"],
            [
                {"id": "sku-1", "quantity": 2, "seller": "1"},
                {"id": "sku-2", "quantity": 1, "seller": "1"},
            ],
        )
        self.mock_checkout.set_client_profile_data.assert_called_once()
        self.mock_checkout.set_shipping_data.assert_called_once()
        self.mock_checkout.set_client_preferences_data.assert_called_once()
        self.mock_checkout.set_marketing_data.assert_called_once()
        self.mock_checkout.get_order_form.assert_not_called()

    def test_execute_returns_none_when_no_items(self):
        source = _full_source_order_form(items=[])

        result = self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=source,
        )

        self.assertIsNone(result)
        self.mock_checkout.create_cart.assert_not_called()

    def test_execute_returns_none_when_create_cart_fails(self):
        self.mock_checkout.create_cart.return_value = None

        result = self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=_full_source_order_form(),
        )

        self.assertIsNone(result)
        self.mock_checkout.add_items.assert_not_called()

    def test_execute_returns_none_when_add_items_fails(self):
        self.mock_checkout.add_items.return_value = None

        result = self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=_full_source_order_form(),
        )

        self.assertIsNone(result)

    def test_attachment_failures_are_best_effort(self):
        self.mock_checkout.set_client_profile_data.return_value = None
        self.mock_checkout.set_shipping_data.return_value = None
        self.mock_checkout.set_client_preferences_data.return_value = None
        self.mock_checkout.set_marketing_data.return_value = None

        result = self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=_full_source_order_form(),
        )

        self.assertEqual(result.order_form_id, "clone-of")

    def test_refetches_source_when_clone_critical_keys_missing(self):
        incomplete = {
            "orderFormId": "source-of",
            "items": [{"id": "sku-1", "quantity": 1, "seller": "1"}],
        }
        self.mock_checkout.get_order_form.return_value = _full_source_order_form()

        result = self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=incomplete,
        )

        self.assertEqual(result.order_form_id, "clone-of")
        self.mock_checkout.get_order_form.assert_called_once_with(
            account_domain="test-account.myvtex.com",
            vtex_account=self.vtex_account,
            order_form_id="source-of",
        )
        self.mock_checkout.set_marketing_data.assert_called_once()

    def test_continues_with_partial_source_when_refetch_fails(self):
        incomplete = {
            "orderFormId": "source-of",
            "items": [{"id": "sku-1", "quantity": 1, "seller": "1"}],
        }
        self.mock_checkout.get_order_form.return_value = None

        result = self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=incomplete,
        )

        self.assertEqual(result.order_form_id, "clone-of")
        self.mock_checkout.set_marketing_data.assert_not_called()
        self.mock_checkout.set_shipping_data.assert_not_called()

    def test_skips_refetch_when_order_form_id_missing(self):
        incomplete = {
            "items": [{"id": "sku-1", "quantity": 1, "seller": "1"}],
        }

        result = self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=incomplete,
        )

        self.assertEqual(result.order_form_id, "clone-of")
        self.mock_checkout.get_order_form.assert_not_called()

    def test_skips_items_without_id(self):
        source = _full_source_order_form(
            items=[
                {"quantity": 1, "seller": "1"},
                {"id": "sku-1", "quantity": 1, "seller": "1"},
            ]
        )

        result = self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=source,
        )

        self.assertEqual(result.order_form_id, "clone-of")
        order_items = self.mock_checkout.add_items.call_args.kwargs["order_items"]
        self.assertEqual(order_items, [{"id": "sku-1", "quantity": 1, "seller": "1"}])

    def test_includes_corporate_fields_when_is_corporate(self):
        source = _full_source_order_form(
            clientProfileData={
                "email": "corp@example.com",
                "firstName": "Corp",
                "lastName": "Ltd",
                "document": "123",
                "documentType": "cnpj",
                "phone": "+5511999999999",
                "isCorporate": True,
                "corporateName": "Corp Ltd",
                "corporateDocument": "00.000.000/0001-00",
                "tradeName": "Corp",
                "stateInscription": "123",
            }
        )

        self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=source,
        )

        payload = self.mock_checkout.set_client_profile_data.call_args.kwargs[
            "client_profile_data"
        ]
        self.assertEqual(payload["corporateName"], "Corp Ltd")
        self.assertTrue(payload["isCorporate"])
