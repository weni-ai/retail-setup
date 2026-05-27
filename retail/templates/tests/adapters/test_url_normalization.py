"""Unit tests for the shared URL normalization helpers. Anchor: FR-003f."""

from django.test import TestCase

from retail.templates.adapters.url_normalization import (
    append_placeholder_if_needed,
    ensure_protocol,
    looks_like_url,
    normalize_url_if_needed,
)


class TestEnsureProtocol(TestCase):
    def test_without_protocol_prepends_https(self):
        self.assertEqual(
            ensure_protocol("example.com/checkout?id="),
            "https://example.com/checkout?id=",
        )

    def test_with_https_protocol_is_unchanged(self):
        self.assertEqual(
            ensure_protocol("https://example.com/checkout"),
            "https://example.com/checkout",
        )

    def test_with_http_protocol_is_unchanged(self):
        self.assertEqual(
            ensure_protocol("http://example.com/checkout"),
            "http://example.com/checkout",
        )

    def test_empty_string_is_unchanged(self):
        self.assertEqual(ensure_protocol(""), "")

    def test_none_is_unchanged(self):
        self.assertIsNone(ensure_protocol(None))


class TestLooksLikeUrl(TestCase):
    def test_with_protocol(self):
        self.assertTrue(looks_like_url("https://example.com"))
        self.assertTrue(looks_like_url("http://example.com"))

    def test_without_protocol_but_with_domain_pattern(self):
        self.assertTrue(looks_like_url("example.com/path"))

    def test_simple_identifier_is_not_a_url(self):
        self.assertFalse(looks_like_url("123"))
        self.assertFalse(looks_like_url("simple-value"))

    def test_empty_or_none_is_not_a_url(self):
        self.assertFalse(looks_like_url(""))
        self.assertFalse(looks_like_url(None))


class TestNormalizeUrlIfNeeded(TestCase):
    def test_with_url_lacking_protocol_prepends_https(self):
        self.assertEqual(
            normalize_url_if_needed("example.com/checkout?id=123"),
            "https://example.com/checkout?id=123",
        )

    def test_with_simple_suffix_passes_through_unchanged(self):
        self.assertEqual(normalize_url_if_needed("123"), "123")

    def test_with_already_https_url_is_unchanged(self):
        self.assertEqual(
            normalize_url_if_needed("https://example.com/page"),
            "https://example.com/page",
        )

    def test_with_empty_string_is_unchanged(self):
        self.assertEqual(normalize_url_if_needed(""), "")

    def test_with_none_is_unchanged(self):
        self.assertIsNone(normalize_url_if_needed(None))


class TestAppendPlaceholderIfNeeded(TestCase):
    def test_appends_when_placeholder_missing(self):
        self.assertEqual(
            append_placeholder_if_needed("https://example.com/checkout?id="),
            "https://example.com/checkout?id={{1}}",
        )

    def test_unchanged_when_placeholder_already_present(self):
        self.assertEqual(
            append_placeholder_if_needed("https://example.com/checkout?id={{1}}"),
            "https://example.com/checkout?id={{1}}",
        )

    def test_does_not_duplicate_placeholder(self):
        result = append_placeholder_if_needed("https://example.com/path={{1}}")
        self.assertNotIn("{{1}}{{1}}", result)
        self.assertEqual(result, "https://example.com/path={{1}}")
