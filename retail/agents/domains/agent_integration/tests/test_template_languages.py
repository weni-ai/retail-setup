"""Catalog the frontend reads to offer template language switching."""

from django.test import SimpleTestCase

from retail.agents.domains.agent_integration.serializers import (
    TemplateLanguageSerializer,
)
from retail.agents.domains.agent_integration.utils import TEMPLATE_LANGUAGES


class TemplateLanguagesCatalogTests(SimpleTestCase):
    def test_catalog_exposes_romanian_with_meta_code(self):
        payload = TemplateLanguageSerializer(TEMPLATE_LANGUAGES, many=True).data

        self.assertEqual(
            [(item["code"], item["display_name"]) for item in payload],
            [
                ("pt_BR", "Português (BR)"),
                ("en", "English (US)"),
                ("es", "Español"),
                ("ro", "Română"),
            ],
        )
