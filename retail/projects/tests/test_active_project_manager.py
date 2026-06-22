from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from retail.projects.models import Project


class ActiveProjectManagerTest(TestCase):
    def setUp(self):
        self.active_uuid = uuid4()
        self.inactive_uuid = uuid4()
        self.vtex_account = "filter-test-store"

        self.active_project = Project.objects.create(
            name="Active Project",
            uuid=self.active_uuid,
            vtex_account=self.vtex_account,
        )
        self.inactive_project = Project.all_objects.create(
            name="Inactive Project",
            uuid=self.inactive_uuid,
            vtex_account="inactive-store",
            is_active=False,
        )

    def test_create_defaults_to_active(self):
        project = Project.objects.create(name="New Project", uuid=uuid4())

        self.assertTrue(project.is_active)

    def test_objects_all_excludes_inactive_projects(self):
        visible_uuids = set(Project.objects.all().values_list("uuid", flat=True))

        self.assertIn(self.active_uuid, visible_uuids)
        self.assertNotIn(self.inactive_uuid, visible_uuids)

    def test_all_objects_includes_inactive_projects(self):
        all_uuids = set(Project.all_objects.all().values_list("uuid", flat=True))

        self.assertIn(self.active_uuid, all_uuids)
        self.assertIn(self.inactive_uuid, all_uuids)

    def test_objects_count_excludes_inactive_projects(self):
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(Project.all_objects.count(), 2)

    def test_objects_get_raises_for_inactive_project(self):
        with self.assertRaises(Project.DoesNotExist):
            Project.objects.get(uuid=self.inactive_uuid)

    def test_all_objects_get_finds_inactive_project(self):
        project = Project.all_objects.get(uuid=self.inactive_uuid)

        self.assertFalse(project.is_active)
        self.assertEqual(project.name, "Inactive Project")

    def test_objects_filter_by_vtex_account_ignores_inactive(self):
        inactive_same_account = Project.all_objects.create(
            name="Inactive Same VTEX",
            uuid=uuid4(),
            vtex_account=self.vtex_account,
            is_active=False,
        )

        matches = list(
            Project.objects.filter(vtex_account=self.vtex_account).values_list(
                "uuid", flat=True
            )
        )

        self.assertEqual(matches, [self.active_uuid])
        self.assertNotIn(inactive_same_account.uuid, matches)

    def test_objects_get_by_vtex_account_raises_when_only_inactive_exists(self):
        self.active_project.is_active = False
        self.active_project.save(update_fields=["is_active"])

        with self.assertRaises(Project.DoesNotExist):
            Project.objects.get(vtex_account=self.vtex_account)

    def test_soft_delete_removes_project_from_default_manager(self):
        self.active_project.is_active = False
        self.active_project.save(update_fields=["is_active"])

        self.assertFalse(Project.objects.filter(uuid=self.active_uuid).exists())
        self.assertTrue(
            Project.all_objects.filter(uuid=self.active_uuid, is_active=False).exists()
        )

    def test_objects_filter_by_uuid_excludes_inactive(self):
        self.assertFalse(Project.objects.filter(uuid=self.inactive_uuid).exists())
        self.assertTrue(Project.all_objects.filter(uuid=self.inactive_uuid).exists())

    def test_reactivation_makes_project_visible_on_default_manager(self):
        self.inactive_project.is_active = True
        self.inactive_project.save(update_fields=["is_active"])

        project = Project.objects.get(uuid=self.inactive_uuid)

        self.assertTrue(project.is_active)
        self.assertEqual(project.name, "Inactive Project")

    def test_modified_on_is_set_on_create(self):
        project = Project.objects.create(name="Timestamped", uuid=uuid4())

        self.assertIsNotNone(project.modified_on)

    def test_modified_on_updates_on_save(self):
        past = timezone.now()
        project = Project.all_objects.create(
            name="Before",
            uuid=uuid4(),
            modified_on=past,
        )

        project.name = "After"
        project.save(update_fields=["name"])
        project.refresh_from_db()

        self.assertGreater(project.modified_on, past)
