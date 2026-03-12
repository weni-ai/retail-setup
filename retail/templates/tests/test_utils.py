from django.test import TestCase

from retail.templates.utils import resolve_template_language, DEFAULT_TEMPLATE_LANGUAGE


class ResolveTemplateLanguageTest(TestCase):
    """Tests for the unified resolve_template_language function."""

    def test_returns_language_from_translation(self):
        result = resolve_template_language(translation={"language": "en_US"})
        self.assertEqual(result, "en_US")

    def test_returns_language_from_agent_config(self):
        result = resolve_template_language(
            agent_config={"initial_template_language": "es"}
        )
        self.assertEqual(result, "es")

    def test_returns_default_when_no_sources(self):
        result = resolve_template_language()
        self.assertEqual(result, DEFAULT_TEMPLATE_LANGUAGE)

    def test_translation_beats_agent_config(self):
        result = resolve_template_language(
            translation={"language": "en_US"},
            agent_config={"initial_template_language": "es"},
        )
        self.assertEqual(result, "en_US")

    def test_skips_none_language_in_translation(self):
        result = resolve_template_language(
            translation={"language": None},
            agent_config={"initial_template_language": "es"},
        )
        self.assertEqual(result, "es")

    def test_skips_empty_string_in_translation(self):
        result = resolve_template_language(
            translation={"language": ""},
            agent_config={"initial_template_language": "es"},
        )
        self.assertEqual(result, "es")

    def test_skips_missing_key_in_agent_config(self):
        result = resolve_template_language(agent_config={"other_key": "value"})
        self.assertEqual(result, DEFAULT_TEMPLATE_LANGUAGE)

    def test_skips_none_in_all_sources(self):
        result = resolve_template_language(
            translation={"language": None},
            agent_config={"initial_template_language": None},
        )
        self.assertEqual(result, DEFAULT_TEMPLATE_LANGUAGE)

    def test_empty_dicts_return_default(self):
        result = resolve_template_language(translation={}, agent_config={})
        self.assertEqual(result, DEFAULT_TEMPLATE_LANGUAGE)

    def test_translation_with_extra_keys_still_works(self):
        result = resolve_template_language(
            translation={"body": "Hello", "language": "fr"}
        )
        self.assertEqual(result, "fr")
