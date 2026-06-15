from unittest.mock import MagicMock
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.clients.exceptions import CustomAPIException
from retail.projects.models import Project, ProjectOnboarding
from retail.vtex.usecases.link_project import LinkProjectDTO, LinkProjectUseCase


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "link-project-usecase-tests",
        }
    }
)
class TestLinkProjectUseCase(TestCase):
    def setUp(self):
        cache.clear()
        self.connect_service = MagicMock()
        self.usecase = LinkProjectUseCase(connect_service=self.connect_service)

    def tearDown(self):
        cache.clear()

    def test_execute_links_via_connect_and_locally(self):
        project = Project.objects.create(uuid=uuid4(), name="Project")
        dto = LinkProjectDTO(vtex_account="mystore", project_uuid=str(project.uuid))

        result = self.usecase.execute(dto)

        self.assertEqual(result, {"success": True})
        self.connect_service.link_vtex_account.assert_called_once_with(
            project_uuid=str(project.uuid),
            vtex_account="mystore",
        )
        project.refresh_from_db()
        self.assertEqual(project.vtex_account, "mystore")

    def test_execute_links_pending_onboarding(self):
        project = Project.objects.create(uuid=uuid4(), name="Project")
        onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore", project=None
        )
        dto = LinkProjectDTO(vtex_account="mystore", project_uuid=str(project.uuid))

        self.usecase.execute(dto)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.project_id, project.id)
        self.assertEqual(onboarding.current_step, "PROJECT_CONFIG")
        self.assertEqual(onboarding.progress, 30)

    def test_execute_when_local_project_missing(self):
        dto = LinkProjectDTO(vtex_account="mystore", project_uuid=str(uuid4()))

        result = self.usecase.execute(dto)

        self.assertEqual(result, {"success": True})
        self.connect_service.link_vtex_account.assert_called_once()

    def test_execute_propagates_connect_error(self):
        project = Project.objects.create(uuid=uuid4(), name="Project")
        self.connect_service.link_vtex_account.side_effect = CustomAPIException(
            detail="already linked", status_code=400
        )
        dto = LinkProjectDTO(vtex_account="mystore", project_uuid=str(project.uuid))

        with self.assertRaises(CustomAPIException):
            self.usecase.execute(dto)

        project.refresh_from_db()
        self.assertIsNone(project.vtex_account)
