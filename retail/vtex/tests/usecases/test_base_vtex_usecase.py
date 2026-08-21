from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.projects.models import Project
from retail.vtex.usecases.base import BaseVtexUseCase


class _ConcreteVtexUseCase(BaseVtexUseCase):
    """Minimal concrete subclass so BaseVtexUseCase can be exercised in tests."""


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-vtex-context",
        }
    }
)
class BaseVtexUseCaseGetVtexContextTest(TestCase):
    def setUp(self):
        cache.clear()
        self.usecase = _ConcreteVtexUseCase()
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="fakeaccount",
        )

    def test_returns_project_account_and_domain(self):
        vtex_account, domain = self.usecase._get_vtex_context(str(self.project.uuid))

        self.assertEqual(vtex_account, "fakeaccount")
        self.assertEqual(domain, "fakeaccount.myvtex.com")

    def test_get_account_domain_returns_domain_only(self):
        domain = self.usecase._get_account_domain(str(self.project.uuid))

        self.assertEqual(domain, "fakeaccount.myvtex.com")

    def test_returns_cached_context_on_second_call(self):
        self.usecase._get_vtex_context(str(self.project.uuid))
        self.project.vtex_account = "changedaccount"
        self.project.save()

        vtex_account, domain = self.usecase._get_vtex_context(str(self.project.uuid))

        self.assertEqual(vtex_account, "fakeaccount")
        self.assertEqual(domain, "fakeaccount.myvtex.com")

    def test_raises_when_project_not_found(self):
        with self.assertRaises(ValueError) as ctx:
            self.usecase._get_vtex_context(str(uuid4()))

        self.assertIn("Project not found", str(ctx.exception))

    def test_raises_when_vtex_account_missing(self):
        project = Project.objects.create(
            name="No Account",
            uuid=uuid4(),
            vtex_account=None,
        )

        with self.assertRaises(ValueError) as ctx:
            self.usecase._get_vtex_context(str(project.uuid))

        self.assertIn("VTEX account not defined", str(ctx.exception))
