from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.onboarding_access import (
    deactivate_onboardings_for_project,
    get_or_create_active_onboarding,
    onboarding_linked_to_active_project_record,
)


class OnboardingAccessTest(TestCase):
    def test_get_or_create_creates_active_onboarding(self):
        onboarding, created = get_or_create_active_onboarding("new-store")

        self.assertTrue(created)
        self.assertTrue(onboarding.is_active)
        self.assertEqual(onboarding.vtex_account, "new-store")

    def test_get_or_create_returns_existing_active_onboarding(self):
        existing = ProjectOnboarding.objects.create(vtex_account="mystore")

        onboarding, created = get_or_create_active_onboarding("mystore")

        self.assertFalse(created)
        self.assertEqual(onboarding.pk, existing.pk)

    def test_get_or_create_creates_new_record_when_only_inactive_exists(self):
        inactive = ProjectOnboarding.all_objects.create(
            vtex_account="mystore",
            is_active=False,
            config={"channels": {"wwc": {"app_uuid": "stale"}}},
        )

        onboarding, created = get_or_create_active_onboarding("mystore")

        self.assertTrue(created)
        self.assertNotEqual(onboarding.pk, inactive.pk)
        self.assertTrue(onboarding.is_active)
        inactive.refresh_from_db()
        self.assertFalse(inactive.is_active)

    def test_deactivate_onboardings_for_project_soft_deletes_linked_records(self):
        project = Project.objects.create(
            name="Store",
            uuid=uuid4(),
            vtex_account="mystore",
        )
        onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=project,
        )

        updated = deactivate_onboardings_for_project(project)

        onboarding.refresh_from_db()
        self.assertEqual(updated, 1)
        self.assertFalse(onboarding.is_active)
        self.assertEqual(onboarding.project_id, project.id)

    def test_deactivate_onboardings_is_idempotent_for_inactive_records(self):
        project = Project.objects.create(
            name="Store",
            uuid=uuid4(),
            vtex_account="mystore",
        )
        onboarding = ProjectOnboarding.all_objects.create(
            vtex_account="mystore",
            project=project,
            is_active=False,
        )

        updated = deactivate_onboardings_for_project(project)

        onboarding.refresh_from_db()
        self.assertEqual(updated, 1)
        self.assertFalse(onboarding.is_active)

    def test_onboarding_linked_to_active_project_record(self):
        project = Project.objects.create(
            name="Store",
            uuid=uuid4(),
            vtex_account="mystore",
        )
        onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=project,
        )

        self.assertTrue(onboarding_linked_to_active_project_record(onboarding))

    def test_onboarding_linked_to_active_project_record_false_for_inactive_project(
        self,
    ):
        inactive_project = Project.all_objects.create(
            name="Inactive",
            uuid=uuid4(),
            vtex_account="mystore",
            is_active=False,
        )
        onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=inactive_project,
        )

        self.assertFalse(onboarding_linked_to_active_project_record(onboarding))

    def test_objects_manager_excludes_inactive_onboarding(self):
        ProjectOnboarding.all_objects.create(
            vtex_account="inactive-store",
            is_active=False,
        )
        ProjectOnboarding.objects.create(vtex_account="active-store")

        self.assertEqual(ProjectOnboarding.objects.count(), 1)
        self.assertEqual(ProjectOnboarding.all_objects.count(), 2)

    def test_active_vtex_account_unique_allows_inactive_duplicate(self):
        ProjectOnboarding.all_objects.create(
            vtex_account="mystore",
            is_active=False,
        )

        active = ProjectOnboarding.objects.create(vtex_account="mystore")

        self.assertTrue(active.is_active)
