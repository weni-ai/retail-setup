from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project
from retail.vtex.usecases.resolve_storefront_origin import resolve_storefront_origin


class ResolveStorefrontOriginTest(TestCase):
    def test_uses_vtex_host_store_netloc(self):
        project = Project.objects.create(
            uuid=uuid4(),
            name="Store",
            vtex_account="teststore",
            config={"vtex_host_store": "https://www.realstore.com.br/"},
        )

        result = resolve_storefront_origin(project)

        self.assertEqual(result.origin, "https://www.realstore.com.br")
        self.assertFalse(result.used_default)

    def test_falls_back_to_myvtex_when_host_store_missing(self):
        project = Project.objects.create(
            uuid=uuid4(),
            name="Store",
            vtex_account="teststore",
            config={},
        )

        result = resolve_storefront_origin(project)

        self.assertEqual(result.origin, "https://teststore.myvtex.com")
        self.assertTrue(result.used_default)
        self.assertNotIn("vtexcommercestable", result.origin)
