"""
Tests for the templates utils module.
"""
from django.test import TestCase, SimpleTestCase

from retail.templates.utils import resolve_template_language, DEFAULT_TEMPLATE_LANGUAGE

from retail.templates.utils import TemplateVariableMapper


class TestTemplateVariableMapper(SimpleTestCase):
    """Tests for TemplateVariableMapper class."""

    def test_extract_variable_labels_simple(self):
        """Should extract variable labels in order of appearance."""
        body = (
            "Hello {{client_name}}, your order {{order_id}} arrives {{delivery_date}}"
        )

        result = TemplateVariableMapper.extract_variable_labels(body)

        self.assertEqual(result, ["client_name", "order_id", "delivery_date"])

    def test_extract_variable_labels_empty_body(self):
        """Should return empty list for empty body."""
        result = TemplateVariableMapper.extract_variable_labels("")
        self.assertEqual(result, [])

        result = TemplateVariableMapper.extract_variable_labels(None)
        self.assertEqual(result, [])

    def test_extract_variable_labels_no_variables(self):
        """Should return empty list when no variables present."""
        body = "Hello, this is a plain message without variables"
        result = TemplateVariableMapper.extract_variable_labels(body)
        self.assertEqual(result, [])

    def test_extract_variable_labels_ignores_numeric(self):
        """Should ignore numeric variables (already converted)."""
        body = "Hello {{1}}, your order {{2}} arrives {{3}}"
        result = TemplateVariableMapper.extract_variable_labels(body)
        self.assertEqual(result, [])

    def test_extract_variable_labels_mixed(self):
        """Should extract only labeled variables, ignoring numeric."""
        body = "Hello {{client_name}}, order {{1}}, value {{valor}}"
        result = TemplateVariableMapper.extract_variable_labels(body)
        self.assertEqual(result, ["client_name", "valor"])

    def test_build_variable_mapping(self):
        """Should build correct mapping from body."""
        body = "Hello {{client_name}}, order {{order_id}}, value {{valor}}"

        result = TemplateVariableMapper.build_variable_mapping(body)

        expected = {"client_name": 1, "order_id": 2, "valor": 3}
        self.assertEqual(result, expected)

    def test_build_variable_mapping_empty(self):
        """Should return empty mapping for empty body."""
        result = TemplateVariableMapper.build_variable_mapping("")
        self.assertEqual(result, {})

    def test_convert_body_to_numeric(self):
        """Should convert labeled variables to numeric format."""
        body = "Hello {{client_name}}, order {{order_id}} for {{valor}}"

        result = TemplateVariableMapper.convert_body_to_numeric(body)

        self.assertEqual(result, "Hello {{1}}, order {{2}} for {{3}}")

    def test_convert_body_to_numeric_preserves_already_numeric(self):
        """Should preserve already numeric variables."""
        body = "Hello {{1}}, order {{2}}"

        result = TemplateVariableMapper.convert_body_to_numeric(body)

        self.assertEqual(result, "Hello {{1}}, order {{2}}")

    def test_convert_body_to_numeric_empty(self):
        """Should handle empty body."""
        result = TemplateVariableMapper.convert_body_to_numeric("")
        self.assertEqual(result, "")

        result = TemplateVariableMapper.convert_body_to_numeric(None)
        self.assertIsNone(result)

    def test_map_labeled_variables_to_numeric_success(self):
        """Should convert labeled variables to numeric keys."""
        variables = {"client_name": "João", "order_id": "123", "valor": "R$ 100"}
        mapping = {"client_name": 1, "order_id": 2, "valor": 3}

        result, unknown = TemplateVariableMapper.map_labeled_variables_to_numeric(
            variables, mapping
        )

        expected = {"1": "João", "2": "123", "3": "R$ 100"}
        self.assertEqual(result, expected)
        self.assertEqual(unknown, [])

    def test_map_labeled_variables_preserves_special_keys(self):
        """Should preserve button and image_url keys."""
        variables = {
            "client_name": "João",
            "button": "https://example.com",
            "image_url": "https://img.com/img.png",
        }
        mapping = {"client_name": 1}

        result, unknown = TemplateVariableMapper.map_labeled_variables_to_numeric(
            variables, mapping
        )

        self.assertEqual(result["1"], "João")
        self.assertEqual(result["button"], "https://example.com")
        self.assertEqual(result["image_url"], "https://img.com/img.png")
        self.assertEqual(unknown, [])

    def test_map_labeled_variables_returns_unknown_labels(self):
        """Should return list of unknown variable labels."""
        variables = {
            "client_name": "João",
            "unknown_var": "value",
            "another_unknown": "value2",
        }
        mapping = {"client_name": 1}

        result, unknown = TemplateVariableMapper.map_labeled_variables_to_numeric(
            variables, mapping
        )

        self.assertEqual(result["1"], "João")
        self.assertIn("unknown_var", unknown)
        self.assertIn("another_unknown", unknown)

    def test_map_labeled_variables_preserves_numeric_keys(self):
        """Should preserve already numeric keys."""
        variables = {"1": "João", "2": "123"}
        mapping = {"client_name": 1}

        result, unknown = TemplateVariableMapper.map_labeled_variables_to_numeric(
            variables, mapping
        )

        self.assertEqual(result["1"], "João")
        self.assertEqual(result["2"], "123")
        self.assertEqual(unknown, [])

    def test_has_labeled_variables_true(self):
        """Should return True when labeled variables present."""
        variables = {"client_name": "João", "button": "url"}
        self.assertTrue(TemplateVariableMapper.has_labeled_variables(variables))

    def test_has_labeled_variables_false_only_numeric(self):
        """Should return False when only numeric keys."""
        variables = {"1": "João", "2": "123"}
        self.assertFalse(TemplateVariableMapper.has_labeled_variables(variables))

    def test_has_labeled_variables_false_with_special_keys(self):
        """Should return False when only special keys and numeric."""
        variables = {"1": "João", "button": "url", "image_url": "img"}
        self.assertFalse(TemplateVariableMapper.has_labeled_variables(variables))

    def test_has_labeled_variables_empty(self):
        """Should return False for empty dict."""
        self.assertFalse(TemplateVariableMapper.has_labeled_variables({}))

    def test_real_world_scenario_cart_abandonment(self):
        """Test real-world cart abandonment template scenario."""
        # Template saved by user (with labels)
        body = "Olá {{cliente_name}}! Você deixou itens no carrinho. Valor: {{valor}}. Finalize: {{link}}"

        # Lambda sends labeled variables
        lambda_variables = {
            "cliente_name": "Maria Silva",
            "valor": "R$ 299,90",
            "link": "https://loja.com/cart/123",
            "button": "cart/123",
            "image_url": "https://loja.com/img/product.jpg",
        }

        # Build mapping from template body
        mapping = TemplateVariableMapper.build_variable_mapping(body)
        self.assertEqual(mapping, {"cliente_name": 1, "valor": 2, "link": 3})

        # Convert to numeric
        result, unknown = TemplateVariableMapper.map_labeled_variables_to_numeric(
            lambda_variables, mapping
        )

        # Verify conversion
        self.assertEqual(result["1"], "Maria Silva")
        self.assertEqual(result["2"], "R$ 299,90")
        self.assertEqual(result["3"], "https://loja.com/cart/123")
        self.assertEqual(result["button"], "cart/123")
        self.assertEqual(result["image_url"], "https://loja.com/img/product.jpg")
        self.assertEqual(unknown, [])

        # Convert body to numeric for Meta API
        numeric_body = TemplateVariableMapper.convert_body_to_numeric(body)
        self.assertEqual(
            numeric_body,
            "Olá {{1}}! Você deixou itens no carrinho. Valor: {{2}}. Finalize: {{3}}",
        )


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
