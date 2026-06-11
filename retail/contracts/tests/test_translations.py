from datetime import datetime, timezone

from django.test import TestCase

from retail.contracts.translations import (
    CONTRACT_PDF_TRANSLATIONS,
    build_contract_email,
    get_contract_pdf_labels,
    resolve_language_prefix,
)


class ContractTranslationsTests(TestCase):
    def test_resolves_known_prefixes_from_full_locale(self):
        self.assertEqual(resolve_language_prefix("pt-br"), "pt")
        self.assertEqual(resolve_language_prefix("es-MX"), "es")
        self.assertEqual(resolve_language_prefix("en-US"), "en")

    def test_falls_back_to_english_for_unknown_or_empty(self):
        self.assertEqual(resolve_language_prefix("fr-FR"), "en")
        self.assertEqual(resolve_language_prefix(""), "en")
        self.assertEqual(resolve_language_prefix(None), "en")

    def test_get_labels_returns_language_specific_title(self):
        self.assertEqual(
            get_contract_pdf_labels("pt-br")["title"],
            CONTRACT_PDF_TRANSLATIONS["pt"]["title"],
        )
        self.assertEqual(
            get_contract_pdf_labels("es")["title"],
            CONTRACT_PDF_TRANSLATIONS["es"]["title"],
        )

    def test_all_languages_share_the_same_keys(self):
        en_keys = set(CONTRACT_PDF_TRANSLATIONS["en"])
        for lang in ("pt", "es"):
            self.assertEqual(set(CONTRACT_PDF_TRANSLATIONS[lang]), en_keys)

    def test_build_contract_email_localizes_subject_body_and_date(self):
        accepted_at = datetime(2026, 6, 10, 14, 32, tzinfo=timezone.utc)

        email_pt = build_contract_email("pt-br", "Growth", "v2.1", accepted_at)
        self.assertEqual(email_pt["subject"], "Seu contrato")
        self.assertIn("Plano: Growth", email_pt["body_html"])
        self.assertIn("10/06/2026", email_pt["body_html"])

        email_en = build_contract_email("en-US", "Growth", "v2.1", accepted_at)
        self.assertEqual(email_en["subject"], "Your contract")
        self.assertIn("06/10/2026", email_en["body_html"])

    def test_build_contract_email_falls_back_plan_placeholder(self):
        accepted_at = datetime(2026, 6, 10, tzinfo=timezone.utc)

        email = build_contract_email("es", "", "v2.1", accepted_at)

        self.assertEqual(email["subject"], "Tu contrato")
        self.assertIn("Plan: -", email["body_html"])
