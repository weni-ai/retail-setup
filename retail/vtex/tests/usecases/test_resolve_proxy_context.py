from unittest.mock import MagicMock
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.clients.exceptions import CustomAPIException
from retail.projects.models import Project
from retail.vtex.exceptions import MerchantAccountNotAllowedError
from retail.vtex.usecases.resolve_proxy_context import (
    SELLER_REGISTER_PATH,
    ResolveProxyContextUseCase,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-resolve-proxy-context",
        }
    }
)
class ResolveProxyContextUseCaseTest(TestCase):
    def setUp(self):
        cache.clear()
        self.mock_service = MagicMock()
        self.usecase = ResolveProxyContextUseCase(vtex_io_service=self.mock_service)
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="fakeaccount",
        )
        self.project_uuid = str(self.project.uuid)

    def test_returns_parent_context_when_merchant_name_absent(self):
        vtex_account, domain = self.usecase.execute(self.project_uuid)

        self.assertEqual(vtex_account, "fakeaccount")
        self.assertEqual(domain, "fakeaccount.myvtex.com")
        self.mock_service.proxy_vtex.assert_not_called()

    def test_returns_parent_context_when_merchant_name_matches_project(self):
        vtex_account, domain = self.usecase.execute(
            self.project_uuid, merchant_name="FakeAccount"
        )

        self.assertEqual(vtex_account, "fakeaccount")
        self.assertEqual(domain, "fakeaccount.myvtex.com")
        self.mock_service.proxy_vtex.assert_not_called()

    def test_rejects_malformed_merchant_name_without_calling_vtex(self):
        with self.assertRaises(MerchantAccountNotAllowedError) as ctx:
            self.usecase.execute(self.project_uuid, merchant_name="bad_name!")

        self.assertEqual(ctx.exception.merchant_name, "bad_name!")
        self.assertEqual(ctx.exception.project_account, "fakeaccount")
        self.mock_service.proxy_vtex.assert_not_called()

    def test_allows_merchant_from_seller_by_id(self):
        self.mock_service.proxy_vtex.return_value = {
            "account": "otherstore",
            "isVtex": True,
        }

        vtex_account, domain = self.usecase.execute(
            self.project_uuid, merchant_name="otherstore"
        )

        self.assertEqual(vtex_account, "otherstore")
        self.assertEqual(domain, "otherstore.myvtex.com")
        self.mock_service.proxy_vtex.assert_called_once_with(
            account_domain="fakeaccount.myvtex.com",
            vtex_account="fakeaccount",
            method="GET",
            path=f"{SELLER_REGISTER_PATH}/otherstore",
            params=None,
        )

    def test_denies_seller_when_is_vtex_is_false(self):
        self.mock_service.proxy_vtex.side_effect = [
            {"account": "otherstore", "isVtex": False},
            [],
        ]

        with self.assertRaises(MerchantAccountNotAllowedError):
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

    def test_allows_merchant_from_list_after_by_id_404(self):
        self.mock_service.proxy_vtex.side_effect = [
            CustomAPIException(detail="not found", status_code=404),
            [{"account": "otherstore", "isVtex": True}],
        ]

        vtex_account, domain = self.usecase.execute(
            self.project_uuid, merchant_name="otherstore"
        )

        self.assertEqual(vtex_account, "otherstore")
        self.assertEqual(domain, "otherstore.myvtex.com")
        list_call = self.mock_service.proxy_vtex.call_args_list[1][1]
        self.assertEqual(list_call["account_domain"], "fakeaccount.myvtex.com")
        self.assertEqual(list_call["vtex_account"], "fakeaccount")
        self.assertEqual(list_call["path"], SELLER_REGISTER_PATH)
        self.assertEqual(
            list_call["params"],
            {"keyword": "otherstore", "from": "0", "to": "100"},
        )

    def test_denies_when_list_has_no_matching_seller(self):
        self.mock_service.proxy_vtex.side_effect = [
            CustomAPIException(detail="not found", status_code=404),
            [{"account": "someoneelse", "isVtex": True}],
        ]

        with self.assertRaises(MerchantAccountNotAllowedError):
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

    def test_does_not_cache_deny_on_non_404_upstream_error(self):
        self.mock_service.proxy_vtex.side_effect = CustomAPIException(
            detail="boom", status_code=500
        )

        with self.assertRaises(CustomAPIException):
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

        self.mock_service.proxy_vtex.reset_mock()
        self.mock_service.proxy_vtex.side_effect = CustomAPIException(
            detail="boom", status_code=500
        )

        with self.assertRaises(CustomAPIException):
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

        self.mock_service.proxy_vtex.assert_called_once()

    def test_cache_hit_skips_seller_lookup(self):
        self.mock_service.proxy_vtex.return_value = {
            "account": "otherstore",
            "isVtex": True,
        }
        self.usecase.execute(self.project_uuid, merchant_name="otherstore")
        self.mock_service.proxy_vtex.reset_mock()

        vtex_account, domain = self.usecase.execute(
            self.project_uuid, merchant_name="otherstore"
        )

        self.assertEqual(vtex_account, "otherstore")
        self.assertEqual(domain, "otherstore.myvtex.com")
        self.mock_service.proxy_vtex.assert_not_called()

    def test_deny_is_cached(self):
        self.mock_service.proxy_vtex.side_effect = [
            CustomAPIException(detail="not found", status_code=404),
            [],
        ]
        with self.assertRaises(MerchantAccountNotAllowedError):
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

        self.mock_service.proxy_vtex.reset_mock()

        with self.assertRaises(MerchantAccountNotAllowedError):
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

        self.mock_service.proxy_vtex.assert_not_called()

    def test_does_not_match_non_string_account(self):
        self.mock_service.proxy_vtex.side_effect = [
            {"account": 123, "isVtex": True},
            [],
        ]

        with self.assertRaises(MerchantAccountNotAllowedError):
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

    def test_does_not_match_seller_name_field(self):
        self.mock_service.proxy_vtex.side_effect = [
            {"name": "otherstore", "account": "someoneelse", "isVtex": True},
            [],
        ]

        with self.assertRaises(MerchantAccountNotAllowedError):
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

    def test_does_not_match_merchant_name_field(self):
        self.mock_service.proxy_vtex.side_effect = [
            {
                "MerchantName": "otherstore",
                "account": "someoneelse",
                "isVtex": True,
            },
            [],
        ]

        with self.assertRaises(MerchantAccountNotAllowedError):
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

    def test_allows_seller_list_payload_from_by_id(self):
        self.mock_service.proxy_vtex.return_value = [
            "skip",
            {"account": "otherstore", "isVtex": True},
        ]

        vtex_account, domain = self.usecase.execute(
            self.project_uuid, merchant_name="otherstore"
        )

        self.assertEqual(vtex_account, "otherstore")
        self.assertEqual(domain, "otherstore.myvtex.com")

    def test_allows_seller_from_list_items_key(self):
        self.mock_service.proxy_vtex.side_effect = [
            CustomAPIException(detail="not found", status_code=404),
            {"items": [{"account": "otherstore", "isVtex": True}]},
        ]

        vtex_account, domain = self.usecase.execute(
            self.project_uuid, merchant_name="otherstore"
        )

        self.assertEqual(vtex_account, "otherstore")
        self.assertEqual(domain, "otherstore.myvtex.com")

    def test_allows_seller_from_list_data_key(self):
        self.mock_service.proxy_vtex.side_effect = [
            CustomAPIException(detail="not found", status_code=404),
            {"data": [{"account": "otherstore", "isVtex": True}]},
        ]

        vtex_account, domain = self.usecase.execute(
            self.project_uuid, merchant_name="otherstore"
        )

        self.assertEqual(vtex_account, "otherstore")
        self.assertEqual(domain, "otherstore.myvtex.com")

    def test_treats_list_404_as_empty(self):
        self.mock_service.proxy_vtex.side_effect = [
            CustomAPIException(detail="not found", status_code=404),
            CustomAPIException(detail="not found", status_code=404),
        ]

        with self.assertRaises(MerchantAccountNotAllowedError):
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

    def test_ignores_non_dict_seller_payload(self):
        self.mock_service.proxy_vtex.side_effect = ["not-a-seller", []]

        with self.assertRaises(MerchantAccountNotAllowedError):
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

    def test_allows_when_is_vtex_is_missing(self):
        self.mock_service.proxy_vtex.return_value = {"account": "otherstore"}

        vtex_account, domain = self.usecase.execute(
            self.project_uuid, merchant_name="otherstore"
        )

        self.assertEqual(vtex_account, "otherstore")
        self.assertEqual(domain, "otherstore.myvtex.com")

    def test_propagates_list_non_404_upstream_error(self):
        self.mock_service.proxy_vtex.side_effect = [
            CustomAPIException(detail="not found", status_code=404),
            CustomAPIException(detail="boom", status_code=503),
        ]

        with self.assertRaises(CustomAPIException) as ctx:
            self.usecase.execute(self.project_uuid, merchant_name="otherstore")

        self.assertEqual(ctx.exception.status_code, 503)

    def test_treats_empty_merchant_name_as_parent(self):
        vtex_account, domain = self.usecase.execute(self.project_uuid, merchant_name="")

        self.assertEqual(vtex_account, "fakeaccount")
        self.assertEqual(domain, "fakeaccount.myvtex.com")
        self.mock_service.proxy_vtex.assert_not_called()

    def test_allows_seller_from_sellers_key(self):
        self.mock_service.proxy_vtex.side_effect = [
            CustomAPIException(detail="not found", status_code=404),
            {"sellers": [{"Account": "otherstore", "IsVtex": True}]},
        ]

        vtex_account, domain = self.usecase.execute(
            self.project_uuid, merchant_name="otherstore"
        )

        self.assertEqual(vtex_account, "otherstore")
        self.assertEqual(domain, "otherstore.myvtex.com")
