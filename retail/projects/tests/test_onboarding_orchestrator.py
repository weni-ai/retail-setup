from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.onboarding_orchestrator import OnboardingOrchestrator


class TestOnboardingOrchestratorPaymentRouting(TestCase):
    """Verifies the One-Click Payment step is wired only for wpp-cloud."""

    ORCHESTRATOR_PATH = "retail.projects.usecases.onboarding_orchestrator"

    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )

        self.fake_channel_usecases = {
            "wwc": MagicMock(),
            "wpp-cloud": MagicMock(),
        }

        self._patch_target("CHANNEL_USECASES", new=self.fake_channel_usecases)
        self._patch_target("ConfigureAgentBuilderUseCase")
        self._patch_target("IntegrateAgentsUseCase")
        self.mock_payment_cls = self._patch_target("ConfigureOneClickPaymentUseCase")

    def _patch_target(self, attr: str, new=None):
        """Starts a patch and registers cleanup before returning the mock.

        Cleanup is registered immediately after start so a later patch
        failure still rolls back what already started — avoids the
        ``Cannot autospec attr ... as it has already been mocked out``
        cascade between tests.
        """
        target = f"{self.ORCHESTRATOR_PATH}.{attr}"
        patcher = patch(target, new=new) if new is not None else patch(target)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def _make_onboarding(self, channel_code: str) -> ProjectOnboarding:
        return ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {channel_code: {}}},
        )

    def test_runs_payment_step_for_wpp_cloud(self):
        self._make_onboarding("wpp-cloud")

        OnboardingOrchestrator().execute("mystore", contents=[])

        self.mock_payment_cls.assert_called_once_with()
        self.mock_payment_cls.return_value.execute.assert_called_once_with("mystore")

    def test_skips_payment_step_for_wwc(self):
        self._make_onboarding("wwc")

        OnboardingOrchestrator().execute("mystore", contents=[])

        self.mock_payment_cls.assert_not_called()

    def test_propagates_failure_and_marks_onboarding_failed(self):
        self._make_onboarding("wpp-cloud")
        self.mock_payment_cls.return_value.execute.side_effect = RuntimeError("boom")

        with patch(
            "retail.projects.usecases.onboarding_orchestrator.mark_onboarding_failed"
        ) as mock_mark_failed, self.assertRaises(RuntimeError):
            OnboardingOrchestrator().execute("mystore", contents=[])

        mock_mark_failed.assert_called_once_with("mystore", "boom")

    def test_raises_when_no_channel_in_config(self):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={},
        )

        with patch(
            "retail.projects.usecases.onboarding_orchestrator.mark_onboarding_failed"
        ), self.assertRaises(ValueError) as ctx:
            OnboardingOrchestrator().execute("mystore", contents=[])

        self.assertIn("No channel configured", str(ctx.exception))

    def test_raises_when_channel_not_registered(self):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"unknown-channel": {}}},
        )

        with patch(
            "retail.projects.usecases.onboarding_orchestrator.mark_onboarding_failed"
        ), self.assertRaises(ValueError) as ctx:
            OnboardingOrchestrator().execute("mystore", contents=[])

        self.assertIn("No channel use case registered", str(ctx.exception))
