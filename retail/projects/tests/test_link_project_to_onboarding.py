from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.link_project_to_onboarding import (
    LinkProjectToOnboardingUseCase,
)


class TestLinkProjectToOnboardingUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="mystore",
        )

    def test_links_project_to_pending_onboarding(self):
        onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
        )

        LinkProjectToOnboardingUseCase.execute(self.project)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.project, self.project)

    def test_sets_project_config_step_and_partial_progress(self):
        """
        Linking the project advances PROJECT_CONFIG to a partial progress
        value; the remaining progress is driven by the pre-crawl channel
        setup task before the NEXUS_CONFIG orchestrator runs.
        """
        from retail.projects.usecases.link_project_to_onboarding import (
            PROJECT_LINKED_PROGRESS,
        )

        onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
        )

        LinkProjectToOnboardingUseCase.execute(self.project)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.current_step, "PROJECT_CONFIG")
        self.assertEqual(onboarding.progress, PROJECT_LINKED_PROGRESS)
        self.assertLess(onboarding.progress, 100)

    def test_does_nothing_when_no_pending_onboarding(self):
        # Should not raise any exception
        LinkProjectToOnboardingUseCase.execute(self.project)

    def test_does_nothing_when_project_has_no_vtex_account(self):
        project = Project.objects.create(name="No VTEX", uuid=uuid4(), vtex_account="")

        # Should not raise any exception
        LinkProjectToOnboardingUseCase.execute(project)

    def test_ignores_onboarding_already_linked_to_project(self):
        other_project = Project.objects.create(
            name="Other", uuid=uuid4(), vtex_account="otherstore"
        )
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=other_project,
        )

        LinkProjectToOnboardingUseCase.execute(self.project)

        # The existing onboarding should remain linked to other_project
        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertEqual(onboarding.project, other_project)

    def test_does_not_link_when_vtex_account_is_none(self):
        project = Project.objects.create(
            name="Null VTEX", uuid=uuid4(), vtex_account=None
        )

        LinkProjectToOnboardingUseCase.execute(project)
        # Should not raise
