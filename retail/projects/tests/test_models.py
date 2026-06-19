from unittest.mock import patch

from django.test import TestCase

from retail.projects.models import ProjectOnboarding

TASK_PATH = "retail.projects.tasks.task_activate_agentic_cx_script"


class TestOnboardingCompletedSignal(TestCase):
    def setUp(self):
        with patch(TASK_PATH):
            self.onboarding = ProjectOnboarding.objects.create(
                vtex_account="teststore",
            )

    @patch(TASK_PATH)
    def test_dispatches_task_on_completed_transition(self, mock_task):
        self.onboarding.completed = True
        self.onboarding.save()

        mock_task.delay.assert_called_once_with("teststore")

    @patch(TASK_PATH)
    def test_does_not_dispatch_when_already_completed(self, mock_task):
        self.onboarding.completed = True
        self.onboarding.save()
        mock_task.reset_mock()

        self.onboarding.save()

        mock_task.delay.assert_not_called()

    @patch(TASK_PATH)
    def test_does_not_dispatch_when_not_completing(self, mock_task):
        self.onboarding.current_page = "setup_channel"
        self.onboarding.save()

        mock_task.delay.assert_not_called()

    @patch(TASK_PATH)
    def test_does_not_dispatch_on_create_with_completed_false(self, mock_task):
        ProjectOnboarding.objects.create(
            vtex_account="newstore",
        )

        mock_task.delay.assert_not_called()

    @patch(TASK_PATH)
    def test_dispatches_on_create_with_completed_true(self, mock_task):
        ProjectOnboarding.objects.create(
            vtex_account="backfillstore",
            completed=True,
        )

        mock_task.delay.assert_called_once_with("backfillstore")
