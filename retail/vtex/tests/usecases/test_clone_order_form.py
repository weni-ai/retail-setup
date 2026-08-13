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

        self.clone_items = [
            {"id": "sku-1", "quantity": 2, "seller": "1"},
            {"id": "sku-2", "quantity": 1, "seller": "1"},
        ]
        self.mock_checkout.create_cart.return_value = {"orderFormId": "clone-of"}
        self.mock_checkout.add_items.return_value = {
            "orderFormId": "clone-of",
            "items": self.clone_items,
        }
        self.mock_checkout.set_client_profile_data.return_value = {}
        self.mock_checkout.set_shipping_data.return_value = {
            "orderFormId": "clone-of",
            "items": self.clone_items,
            "shippingData": {
                "selectedAddresses": [
                    {"postalCode": "01310-100", "addressId": "clone-addr"}
                ]
            },
        }
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
        self.assertEqual(self.mock_checkout.set_shipping_data.call_count, 2)
        address_payload = self.mock_checkout.set_shipping_data.call_args_list[0].kwargs[
            "shipping_data"
        ]
        self.assertEqual(
            address_payload["selectedAddresses"], [{"postalCode": "01310-100"}]
        )
        self.assertNotIn("logisticsInfo", address_payload)
        sla_payload = self.mock_checkout.set_shipping_data.call_args_list[1].kwargs[
            "shipping_data"
        ]
        self.assertEqual(
            sla_payload["logisticsInfo"],
            [
                {
                    "itemIndex": 0,
                    "selectedSla": "Normal",
                    "selectedDeliveryChannel": "delivery",
                }
            ],
        )
        self.assertEqual(
            sla_payload["selectedAddresses"],
            [{"postalCode": "01310-100", "addressId": "clone-addr"}],
        )
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

    def test_skips_gift_and_assembly_child_items(self):
        source = _full_source_order_form(
            items=[
                {"id": "sku-1", "quantity": 1, "seller": "1"},
                {"id": "sku-gift", "quantity": 1, "seller": "1", "isGift": True},
                {
                    "id": "sku-child",
                    "quantity": 1,
                    "seller": "1",
                    "parentItemIndex": 0,
                },
            ]
        )

        self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=source,
        )

        order_items = self.mock_checkout.add_items.call_args.kwargs["order_items"]
        self.assertEqual(order_items, [{"id": "sku-1", "quantity": 1, "seller": "1"}])

    def test_shipping_drops_source_address_id_and_null_fields(self):
        source = _full_source_order_form(
            shippingData={
                "selectedAddresses": [
                    {
                        "addressType": "search",
                        "receiverName": None,
                        "addressId": "-1782765895361",
                        "isDisposable": True,
                        "postalCode": "04040",
                        "geoCoordinates": [-99.15, 19.34],
                    }
                ],
                "logisticsInfo": [],
            }
        )

        self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=source,
        )

        payload = self.mock_checkout.set_shipping_data.call_args.kwargs["shipping_data"]
        address = payload["selectedAddresses"][0]
        self.assertEqual(address["addressType"], "search")
        self.assertEqual(address["postalCode"], "04040")
        self.assertNotIn("addressId", address)
        self.assertNotIn("receiverName", address)
        self.assertEqual(self.mock_checkout.set_shipping_data.call_count, 1)

    def test_shipping_remaps_logistics_indexes_to_clone_items(self):
        source = _full_source_order_form(
            items=[
                {"id": "sku-1", "quantity": 1, "seller": "1"},
                {"id": "sku-unavailable", "quantity": 1, "seller": "1"},
            ],
            shippingData={
                "selectedAddresses": [{"postalCode": "04040", "country": "MEX"}],
                "logisticsInfo": [
                    {
                        "itemIndex": 0,
                        "selectedSla": "Pickup A",
                        "selectedDeliveryChannel": "pickup-in-point",
                        "pickupPointId": "PP135",
                    },
                    {
                        "itemIndex": 1,
                        "selectedSla": "Pickup A",
                        "selectedDeliveryChannel": "pickup-in-point",
                        "pickupPointId": "PP135",
                    },
                ],
            },
        )
        self.mock_checkout.add_items.return_value = {
            "orderFormId": "clone-of",
            "items": [{"id": "sku-1", "quantity": 1, "seller": "1"}],
        }
        self.mock_checkout.set_shipping_data.return_value = {
            "items": [{"id": "sku-1", "quantity": 1, "seller": "1"}],
            "shippingData": {
                "selectedAddresses": [
                    {"postalCode": "04040", "addressId": "clone-addr"}
                ]
            },
        }

        self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=source,
        )

        sla_payload = self.mock_checkout.set_shipping_data.call_args_list[1].kwargs[
            "shipping_data"
        ]
        self.assertEqual(
            sla_payload["logisticsInfo"],
            [
                {
                    "itemIndex": 0,
                    "selectedSla": "Pickup A",
                    "selectedDeliveryChannel": "pickup-in-point",
                    "pickupPointId": "PP135",
                }
            ],
        )
        self.assertEqual(
            sla_payload["selectedAddresses"],
            [{"postalCode": "04040", "addressId": "clone-addr"}],
        )

    def test_remap_logistics_skips_incomplete_and_unmatched_rows(self):
        remapped = self.use_case._remap_logistics_info(
            source_items=[{"id": "sku-1", "seller": "1"}],
            source_logistics=[
                {"selectedSla": "Normal"},
                {"itemIndex": 99, "selectedSla": "Normal"},
                {
                    "itemIndex": 0,
                    "selectedSla": "Normal",
                    "selectedDeliveryChannel": "delivery",
                },
            ],
            clone_items=[{"id": "sku-1", "seller": "1"}],
        )

        self.assertEqual(
            remapped,
            [
                {
                    "itemIndex": 0,
                    "selectedSla": "Normal",
                    "selectedDeliveryChannel": "delivery",
                }
            ],
        )

    def test_remap_logistics_returns_empty_when_clone_has_no_items(self):
        remapped = self.use_case._remap_logistics_info(
            source_items=[{"id": "sku-1", "seller": "1"}],
            source_logistics=[{"itemIndex": 0, "selectedSla": "Normal"}],
            clone_items=[],
        )

        self.assertEqual(remapped, [])

    def test_skips_sla_selection_when_address_step_fails(self):
        self.mock_checkout.set_shipping_data.return_value = None

        result = self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=_full_source_order_form(),
        )

        self.assertEqual(result.order_form_id, "clone-of")
        self.assertEqual(self.mock_checkout.set_shipping_data.call_count, 1)

    def test_sla_selection_failure_is_best_effort(self):
        self.mock_checkout.set_shipping_data.side_effect = [
            {
                "items": self.clone_items,
                "shippingData": {
                    "selectedAddresses": [
                        {"postalCode": "01310-100", "addressId": "clone-addr"}
                    ]
                },
            },
            None,
        ]

        result = self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=_full_source_order_form(),
        )

        self.assertEqual(result.order_form_id, "clone-of")
        self.assertEqual(self.mock_checkout.set_shipping_data.call_count, 2)

    def test_sla_payload_falls_back_to_source_addresses_when_clone_omits_them(self):
        self.mock_checkout.set_shipping_data.return_value = {
            "items": self.clone_items,
            "shippingData": {},
        }

        self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=_full_source_order_form(),
        )

        sla_payload = self.mock_checkout.set_shipping_data.call_args_list[1].kwargs[
            "shipping_data"
        ]
        self.assertEqual(
            sla_payload["selectedAddresses"], [{"postalCode": "01310-100"}]
        )

    def test_shipping_with_logistics_only_skips_address_step(self):
        source = _full_source_order_form(
            shippingData={
                "logisticsInfo": [
                    {
                        "itemIndex": 0,
                        "selectedSla": "Normal",
                        "selectedDeliveryChannel": "delivery",
                    }
                ],
            }
        )

        self.use_case.execute(
            project_uuid=self.project_uuid,
            vtex_account=self.vtex_account,
            order_form=source,
        )

        self.assertEqual(self.mock_checkout.set_shipping_data.call_count, 1)
        payload = self.mock_checkout.set_shipping_data.call_args.kwargs["shipping_data"]
        self.assertNotIn("selectedAddresses", payload)
        self.assertEqual(
            payload["logisticsInfo"],
            [
                {
                    "itemIndex": 0,
                    "selectedSla": "Normal",
                    "selectedDeliveryChannel": "delivery",
                }
            ],
        )
