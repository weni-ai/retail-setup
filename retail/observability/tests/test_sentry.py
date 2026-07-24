from unittest.mock import MagicMock, patch

from django.test import TestCase

from retail.observability.sentry import (
    fingerprint_with_vtex_account,
    sentry_error_scope,
)


class SentryErrorScopeTest(TestCase):
    def setUp(self):
        self.scope = MagicMock()
        scope_cm = MagicMock()
        scope_cm.__enter__.return_value = self.scope
        scope_cm.__exit__.return_value = False
        self.new_scope_patcher = patch(
            "retail.observability.sentry.sentry_sdk.new_scope",
            return_value=scope_cm,
        )
        self.new_scope_patcher.start()
        self.addCleanup(self.new_scope_patcher.stop)

    def test_sets_fingerprint_tags_and_context(self):
        with sentry_error_scope(
            fingerprint=["cart-service", "vtex-api-error", "429"],
            tags={"vtex_account": "lojasrede", "http_status": 429},
            context={"detail": "Too many requests"},
        ):
            pass

        self.assertEqual(
            self.scope.fingerprint, ["cart-service", "vtex-api-error", "429"]
        )
        self.scope.set_tag.assert_any_call("vtex_account", "lojasrede")
        self.scope.set_tag.assert_any_call("http_status", "429")
        self.scope.set_context.assert_called_once_with(
            "error_details", {"detail": "Too many requests"}
        )

    def test_skips_none_tag_values(self):
        with sentry_error_scope(
            fingerprint=["x"],
            tags={"vtex_account": "lojasrede", "http_status": None},
        ):
            pass

        tagged_keys = [call.args[0] for call in self.scope.set_tag.call_args_list]
        self.assertIn("vtex_account", tagged_keys)
        self.assertNotIn("http_status", tagged_keys)

    def test_truncates_oversized_tag_value(self):
        with sentry_error_scope(fingerprint=["x"], tags={"detail": "a" * 500}):
            pass

        _, value = self.scope.set_tag.call_args.args
        self.assertEqual(len(value), 200)
        self.assertTrue(value.endswith("…"))

    def test_does_not_set_context_when_absent(self):
        with sentry_error_scope(fingerprint=["x"]):
            pass

        self.scope.set_context.assert_not_called()

    def test_enrichment_failure_does_not_break_block(self):
        self.scope.set_tag.side_effect = RuntimeError("sentry down")

        executed = False
        with sentry_error_scope(fingerprint=["x"], tags={"a": "b"}):
            executed = True

        self.assertTrue(executed)

    def test_fingerprint_with_vtex_account_appends_account(self):
        result = fingerprint_with_vtex_account(
            ["cart-service", "vtex-api-error", "429"],
            {"vtex_account": "lojasrede"},
        )
        self.assertEqual(
            result,
            ["cart-service", "vtex-api-error", "429", "lojasrede"],
        )

    def test_fingerprint_with_vtex_account_skips_when_missing(self):
        result = fingerprint_with_vtex_account(
            ["cart-service", "vtex-api-error", "429"],
            {"project_uuid": "abc"},
        )
        self.assertEqual(result, ["cart-service", "vtex-api-error", "429"])

    def test_fingerprint_with_vtex_account_does_not_duplicate(self):
        result = fingerprint_with_vtex_account(
            ["cart-service", "429", "lojasrede"],
            {"vtex_account": "lojasrede"},
        )
        self.assertEqual(result, ["cart-service", "429", "lojasrede"])
