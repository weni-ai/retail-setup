from datetime import datetime, timezone as dt_timezone

from django.test import TestCase

from retail.contracts.translations import (
    CONTRACT_PDF_TRANSLATIONS,
    ORDER_FORM_PARTIALS,
    apply_local_offset,
    build_contract_email,
    build_electronic_acceptance_notice,
    format_acceptance_date_only,
    format_acceptance_datetime,
    get_contract_pdf_labels,
    get_order_form_partial,
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

    def test_get_order_form_partial_returns_language_specific_template(self):
        self.assertEqual(
            get_order_form_partial("pt-br"),
            ORDER_FORM_PARTIALS["pt"],
        )
        self.assertEqual(
            get_order_form_partial("en-US"),
            ORDER_FORM_PARTIALS["en"],
        )
        self.assertEqual(
            get_order_form_partial("es-MX"),
            ORDER_FORM_PARTIALS["es"],
        )

    def test_get_order_form_partial_falls_back_to_english(self):
        self.assertEqual(
            get_order_form_partial("fr-FR"),
            ORDER_FORM_PARTIALS["en"],
        )

    def test_build_contract_email_localizes_subject_body_and_date(self):
        accepted_at = datetime(2026, 6, 10, 14, 32, tzinfo=dt_timezone.utc)

        email_pt = build_contract_email("pt-br", "Growth", "v2.1", accepted_at)
        self.assertEqual(email_pt["subject"], "Seu contrato")
        self.assertIn("Plano: Growth", email_pt["body_html"])
        self.assertIn("10/06/2026", email_pt["body_html"])

        email_en = build_contract_email("en-US", "Growth", "v2.1", accepted_at)
        self.assertEqual(email_en["subject"], "Your contract")
        self.assertIn("06/10/2026", email_en["body_html"])

    def test_build_contract_email_falls_back_plan_placeholder(self):
        accepted_at = datetime(2026, 6, 10, tzinfo=dt_timezone.utc)

        email = build_contract_email("es", "", "v2.1", accepted_at)

        self.assertEqual(email["subject"], "Tu contrato")
        self.assertIn("Plan: -", email["body_html"])

    def test_format_acceptance_datetime_portuguese(self):
        accepted_at = datetime(2025, 6, 10, 17, 32, tzinfo=dt_timezone.utc)

        formatted = format_acceptance_datetime(accepted_at, "-03:00", "pt-br")

        self.assertEqual(formatted, "10 de junho de 2025, às 14h32min (UTC-03:00)")

    def test_format_acceptance_datetime_english(self):
        accepted_at = datetime(2025, 6, 10, 17, 32, tzinfo=dt_timezone.utc)

        formatted = format_acceptance_datetime(accepted_at, "-03:00", "en-US")

        self.assertEqual(formatted, "June 10, 2025, at 2:32 PM (UTC-03:00)")

    def test_format_acceptance_datetime_spanish(self):
        accepted_at = datetime(2025, 6, 10, 17, 32, tzinfo=dt_timezone.utc)

        formatted = format_acceptance_datetime(accepted_at, "-03:00", "es-MX")

        self.assertEqual(formatted, "10 de junio de 2025, a las 14:32 (UTC-03:00)")

    def test_apply_local_offset_ignores_invalid_offset(self):
        accepted_at = datetime(2025, 6, 10, 17, 32, tzinfo=dt_timezone.utc)

        result = apply_local_offset(accepted_at, "invalid")

        self.assertEqual(result, accepted_at)

    def test_apply_local_offset_adjusts_naive_datetime(self):
        accepted_at = datetime(2025, 6, 10, 17, 32)

        result = apply_local_offset(accepted_at, "-03:00")

        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 32)

    def test_build_electronic_acceptance_notice_includes_formatted_date(self):
        accepted_at = datetime(2025, 6, 10, 17, 32, tzinfo=dt_timezone.utc)

        notice = build_electronic_acceptance_notice(
            language="pt-br",
            accepted_at=accepted_at,
            local_offset="-03:00",
            acceptance_id="acceptance-uuid",
        )

        self.assertIn("acceptance-uuid", notice)
        self.assertIn("14h32min", notice)
        self.assertIn("VTEX CX", notice)

    def test_format_acceptance_date_only_portuguese(self):
        accepted_at = datetime(2025, 6, 10, 17, 32, tzinfo=dt_timezone.utc)

        formatted = format_acceptance_date_only(accepted_at, "-03:00", "pt-br")

        self.assertEqual(formatted, "10 de junho de 2025")

    def test_format_acceptance_date_only_english(self):
        accepted_at = datetime(2025, 6, 10, 17, 32, tzinfo=dt_timezone.utc)

        formatted = format_acceptance_date_only(accepted_at, "-03:00", "en-US")

        self.assertEqual(formatted, "June 10, 2025")

    def test_format_acceptance_date_only_spanish(self):
        accepted_at = datetime(2025, 6, 10, 17, 32, tzinfo=dt_timezone.utc)

        formatted = format_acceptance_date_only(accepted_at, "-03:00", "es-MX")

        self.assertEqual(formatted, "10 de junio de 2025")
