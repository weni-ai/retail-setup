from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project
from retail.projects.usecases.get_project_vtex_account import (
    GetProjectVtexAccountUseCase,
)


class GetProjectVtexAccountUseCaseTest(TestCase):
    def setUp(self):
        self.use_case = GetProjectVtexAccountUseCase()
        self.parent = Project.objects.create(
            name="Parent",
            uuid=uuid4(),
            vtex_account="parentstore",
        )

    def test_returns_project_vtex_account(self):
        result = self.use_case.execute(str(self.parent.uuid))

        self.assertEqual(result, "parentstore")

    def test_returns_none_when_project_has_no_vtex_account(self):
        project = Project.objects.create(
            name="Empty",
            uuid=uuid4(),
            vtex_account=None,
        )

        self.assertIsNone(self.use_case.execute(str(project.uuid)))

    def test_returns_none_when_project_does_not_exist(self):
        self.assertIsNone(self.use_case.execute(str(uuid4())))

    def test_copilot_returns_parent_vtex_account(self):
        copilot = Project.objects.create(
            name="Copilot",
            uuid=uuid4(),
            vtex_account=None,
            is_live_desk_copilot=True,
            parent_project=self.parent,
        )

        self.assertEqual(self.use_case.execute(str(copilot.uuid)), "parentstore")

    def test_copilot_returns_none_when_parent_has_no_vtex_account(self):
        parent = Project.objects.create(
            name="Parent No VTEX",
            uuid=uuid4(),
            vtex_account=None,
        )
        copilot = Project.objects.create(
            name="Copilot",
            uuid=uuid4(),
            is_live_desk_copilot=True,
            parent_project=parent,
        )

        self.assertIsNone(self.use_case.execute(str(copilot.uuid)))

    def test_copilot_reads_vtex_account_from_inactive_parent(self):
        parent = Project.all_objects.create(
            name="Inactive Parent",
            uuid=uuid4(),
            vtex_account="inactivestore",
            is_active=False,
        )
        copilot = Project.objects.create(
            name="Copilot",
            uuid=uuid4(),
            is_live_desk_copilot=True,
            parent_project=parent,
        )

        self.assertEqual(self.use_case.execute(str(copilot.uuid)), "inactivestore")

    def test_resolve_vtex_account_returns_none_when_parent_id_is_missing(self):
        copilot = Project(
            name="Copilot",
            uuid=uuid4(),
            is_live_desk_copilot=True,
        )

        self.assertIsNone(copilot.resolve_vtex_account())

    def test_resolve_vtex_account_returns_none_when_parent_row_is_missing(self):
        copilot = Project(
            name="Copilot",
            uuid=uuid4(),
            is_live_desk_copilot=True,
        )
        copilot.parent_project_id = 999999

        self.assertIsNone(copilot.resolve_vtex_account())
