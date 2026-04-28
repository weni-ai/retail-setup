from django.test import TestCase

from retail.broadcasts.services.trial_suspension_service import (
    TrialSuspensionService,
)


class TrialSuspensionServiceTest(TestCase):
    """The service is a placeholder until feature/suspend-trial-project
    is merged. It must only log the intent without raising."""

    def test_suspend_logs_without_raising(self):
        service = TrialSuspensionService()

        with self.assertLogs(
            "retail.broadcasts.services.trial_suspension_service", level="WARNING"
        ) as captured:
            service.suspend(project_uuid="project-1", limit=100)

        self.assertTrue(
            any(
                "[BROADCAST_TRACKING] suspension_placeholder" in line
                for line in captured.output
            )
        )
        self.assertTrue(any("project-1" in line for line in captured.output))
