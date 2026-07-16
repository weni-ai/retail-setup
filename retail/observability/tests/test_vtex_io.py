from django.test import TestCase

from retail.observability.vtex_io import (
    build_vtex_io_proxy_sentry_metadata,
    normalize_proxy_path,
)


class NormalizeProxyPathTest(TestCase):
    def test_collapses_uuid_and_order_id(self):
        path = "/api/oms/pvt/orders/1557825995418-01"
        self.assertEqual(
            normalize_proxy_path(path),
            "/api/oms/pvt/orders",
        )

    def test_collapses_uuid_segment(self):
        path = (
            "/api/catalog/pvt/product/" "b3af2657-d6a3-4a36-b6bf-a70eb8704752/details"
        )
        self.assertEqual(
            normalize_proxy_path(path),
            "/api/catalog/pvt/product",
        )

    def test_strips_query_string(self):
        self.assertEqual(
            normalize_proxy_path("/api/oms/pvt/orders?page=2"),
            "/api/oms/pvt/orders",
        )

    def test_returns_root_for_empty_path(self):
        self.assertEqual(normalize_proxy_path(""), "/")
        self.assertEqual(normalize_proxy_path("   "), "/")

    def test_returns_root_for_slash_only_path(self):
        self.assertEqual(normalize_proxy_path("/"), "/")


class BuildVtexIoProxySentryMetadataTest(TestCase):
    def test_builds_tags_and_fingerprint_for_generic_proxy(self):
        metadata = build_vtex_io_proxy_sentry_metadata(
            service="vtex_io_proxy",
            vtex_account="lojasrede",
            method="GET",
            path="/api/oms/pvt/orders/123-01",
        )

        self.assertEqual(
            metadata["sentry_fingerprint_prefix"],
            ["vtex_io_proxy", "GET", "/api/oms/pvt/orders", "lojasrede"],
        )
        self.assertEqual(metadata["sentry_tags"]["vtex_account"], "lojasrede")
        self.assertEqual(metadata["sentry_tags"]["proxy_path"], "/api/oms/pvt/orders")

    def test_omits_path_when_not_provided(self):
        metadata = build_vtex_io_proxy_sentry_metadata(
            service="vtex_io_proxy_payment_transaction",
            vtex_account="lojasrede",
            method="POST",
        )

        self.assertNotIn("proxy_path", metadata["sentry_tags"])
        self.assertEqual(
            metadata["sentry_fingerprint_prefix"],
            ["vtex_io_proxy_payment_transaction", "POST", "lojasrede"],
        )
