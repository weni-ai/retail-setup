from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.tests.fakes import FakeVtexIOClient
from retail.vtex.usecases.resolve_order_origin_account import (
    ResolveOrderOriginAccountUseCase,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "order-origin-account-tests",
        }
    }
)
class ResolveOrderOriginAccountUseCaseTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Columbia",
            vtex_account="columbiamx",
            config={
                "vtex_config": {
                    "vtex_sub_accounts": ["columbiamx", "martimx"],
                }
            },
        )
        self.oms_client = FakeVtexIOClient(hostname="martimx", order_id="v123-01")
        self.usecase = ResolveOrderOriginAccountUseCase(
            vtex_io_service=VtexIOService(client=self.oms_client)
        )

    def test_returns_store_name_from_hostname(self):
        result = self.usecase.execute("v123-01", "columbiamx", self.project)

        self.assertEqual(result, "martimx")
        self.assertEqual(
            self.oms_client.proxy_calls,
            [
                {
                    "account_domain": "columbiamx.myvtex.com",
                    "vtex_account": "columbiamx",
                    "method": "GET",
                    "path": "/api/oms/pvt/orders/v123-01",
                }
            ],
        )

    def test_caches_origin_account(self):
        first = self.usecase.execute("v123-01", "columbiamx", self.project)
        second = self.usecase.execute("v123-01", "columbiamx", self.project)

        self.assertEqual(first, "martimx")
        self.assertEqual(second, "martimx")
        self.assertEqual(len(self.oms_client.proxy_calls), 1)

    def test_returns_none_when_lookup_fails(self):
        self.oms_client.proxy_error = Exception("oms down")
        self.assertIsNone(self.usecase.execute("v123-01", "columbiamx", self.project))

    def test_returns_none_when_hostname_missing(self):
        self.oms_client.proxy_response = {"orderId": "v123-01"}
        self.assertIsNone(self.usecase.execute("v123-01", "columbiamx", self.project))

    def test_returns_none_when_order_id_missing(self):
        self.assertIsNone(self.usecase.execute("", "columbiamx", self.project))
        self.assertEqual(self.oms_client.proxy_calls, [])

    def test_returns_none_for_non_dict_response(self):
        self.oms_client.proxy_response = []
        self.assertIsNone(self.usecase.execute("v123-01", "columbiamx", self.project))
