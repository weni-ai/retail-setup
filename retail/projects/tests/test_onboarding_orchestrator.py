from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.onboarding_orchestrator import (
    CRAWL_KICKOFF_PROGRESS,
    OnboardingOrchestrator,
)

CRAWL_URL = "https://www.mystore.com.br/"


class TestOnboardingOrchestrator(TestCase):
    """Generic flow tests (no payment routing involved)."""

    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            current_step="PROJECT_CONFIG",
            progress=100,
            config={
                "channels": {
                    "wwc": {
                        "app_uuid": str(uuid4()),
                    }
                }
            },
        )

    @patch("retail.projects.usecases.onboarding_orchestrator.InitiateCrawlUseCase")
    @patch("retail.projects.usecases.onboarding_orchestrator.IntegrateAgentsUseCase")
    @patch(
        "retail.projects.usecases.onboarding_orchestrator.ConfigureAgentBuilderUseCase"
    )
    def test_runs_crawl_agent_builder_then_integrate(
        self, mock_agent_builder_cls, mock_integrate_cls, mock_initiate_cls
    ):
        mock_initiate = MagicMock()
        mock_initiate_cls.return_value = mock_initiate
        mock_agent_builder = MagicMock()
        mock_agent_builder_cls.return_value = mock_agent_builder
        mock_integrate = MagicMock()
        mock_integrate_cls.return_value = mock_integrate

        OnboardingOrchestrator().execute("mystore", CRAWL_URL)

        mock_initiate.execute.assert_called_once_with(
            self.project, "mystore", CRAWL_URL
        )
        mock_agent_builder.execute.assert_called_once_with("mystore")
        mock_integrate.execute.assert_called_once_with("mystore")

    @patch("retail.projects.usecases.onboarding_orchestrator.InitiateCrawlUseCase")
    @patch("retail.projects.usecases.onboarding_orchestrator.IntegrateAgentsUseCase")
    @patch(
        "retail.projects.usecases.onboarding_orchestrator.ConfigureAgentBuilderUseCase"
    )
    def test_transitions_to_nexus_config_and_marks_crawl_kickoff(
        self, mock_agent_builder_cls, _mock_integrate_cls, mock_initiate_cls
    ):
        """The orchestrator must mark NEXUS_CONFIG and crawl kickoff progress."""
        mock_initiate_cls.return_value = MagicMock()
        progress_at_agent_time = {}

        def capture(vtex_account):
            onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
            progress_at_agent_time["step"] = onboarding.current_step
            progress_at_agent_time["progress"] = onboarding.progress

        mock_agent_builder = MagicMock()
        mock_agent_builder.execute.side_effect = capture
        mock_agent_builder_cls.return_value = mock_agent_builder

        OnboardingOrchestrator().execute("mystore", CRAWL_URL)

        self.assertEqual(progress_at_agent_time["step"], "NEXUS_CONFIG")
        self.assertEqual(progress_at_agent_time["progress"], CRAWL_KICKOFF_PROGRESS)

    @patch("retail.projects.usecases.onboarding_orchestrator.mark_onboarding_failed")
    @patch("retail.projects.usecases.onboarding_orchestrator.InitiateCrawlUseCase")
    @patch("retail.projects.usecases.onboarding_orchestrator.IntegrateAgentsUseCase")
    @patch(
        "retail.projects.usecases.onboarding_orchestrator.ConfigureAgentBuilderUseCase"
    )
    def test_marks_failed_when_agent_builder_fails(
        self,
        mock_agent_builder_cls,
        mock_integrate_cls,
        mock_initiate_cls,
        mock_mark_failed,
    ):
        mock_initiate_cls.return_value = MagicMock()
        mock_agent_builder = MagicMock()
        mock_agent_builder.execute.side_effect = RuntimeError("nexus down")
        mock_agent_builder_cls.return_value = mock_agent_builder

        mock_integrate = MagicMock()
        mock_integrate_cls.return_value = mock_integrate

        with self.assertRaises(RuntimeError):
            OnboardingOrchestrator().execute("mystore", CRAWL_URL)

        mock_mark_failed.assert_called_once()
        mock_integrate.execute.assert_not_called()

    @patch("retail.projects.usecases.onboarding_orchestrator.mark_onboarding_failed")
    @patch("retail.projects.usecases.onboarding_orchestrator.InitiateCrawlUseCase")
    @patch("retail.projects.usecases.onboarding_orchestrator.IntegrateAgentsUseCase")
    @patch(
        "retail.projects.usecases.onboarding_orchestrator.ConfigureAgentBuilderUseCase"
    )
    def test_marks_failed_when_integrate_fails(
        self,
        mock_agent_builder_cls,
        mock_integrate_cls,
        mock_initiate_cls,
        mock_mark_failed,
    ):
        mock_initiate_cls.return_value = MagicMock()
        mock_agent_builder = MagicMock()
        mock_agent_builder_cls.return_value = mock_agent_builder

        mock_integrate = MagicMock()
        mock_integrate.execute.side_effect = RuntimeError("nexus error")
        mock_integrate_cls.return_value = mock_integrate

        with self.assertRaises(RuntimeError):
            OnboardingOrchestrator().execute("mystore", CRAWL_URL)

        mock_mark_failed.assert_called_once()

    def test_does_not_invoke_channel_usecase(self):
        """
        Channel creation now runs pre-crawl. The post-crawl orchestrator
        must not reference any channel use case.
        """
        import inspect

        from retail.projects.usecases import onboarding_orchestrator

        source = inspect.getsource(onboarding_orchestrator)
        self.assertNotIn("ConfigureWPPCloudUseCase", source)
        self.assertNotIn("ConfigureWWCUseCase", source)

    def test_does_not_invoke_upload_use_case(self):
        """
        Content upload now lives in ``UploadNexusContentsUseCase`` and
        runs in background via ``task_upload_nexus_contents``. The inline
        orchestrator must not reference the upload use case at all.
        """
        import inspect

        from retail.projects.usecases import onboarding_orchestrator

        source = inspect.getsource(onboarding_orchestrator)
        self.assertNotIn("UploadNexusContentsUseCase", source)
        self.assertNotIn("upload_contents", source)


class TestOnboardingOrchestratorPaymentRouting(TestCase):
    """Verifies the One-Click Payment step is wired only for wpp-cloud."""

    ORCHESTRATOR_PATH = "retail.projects.usecases.onboarding_orchestrator"
    CRAWL_URL = CRAWL_URL

    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )

        self._patch_target("InitiateCrawlUseCase")
        self._patch_target("ConfigureAgentBuilderUseCase")
        self.mock_integrate_cls = self._patch_target("IntegrateAgentsUseCase")
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

        OnboardingOrchestrator().execute("mystore", self.CRAWL_URL)

        self.mock_payment_cls.assert_called_once_with()
        self.mock_payment_cls.return_value.execute.assert_called_once_with("mystore")

    def test_skips_payment_step_for_wwc(self):
        self._make_onboarding("wwc")

        OnboardingOrchestrator().execute("mystore", self.CRAWL_URL)

        self.mock_payment_cls.assert_not_called()

    def test_payment_runs_before_integrate_agents_for_wpp_cloud(self):
        """OCP must execute before agent integration so the One-Click
        Payment agent can read the published flow_id as a credential."""
        self._make_onboarding("wpp-cloud")
        call_order = []
        self.mock_payment_cls.return_value.execute.side_effect = (
            lambda *_: call_order.append("ocp")
        )
        self.mock_integrate_cls.return_value.execute.side_effect = (
            lambda *_: call_order.append("integrate")
        )

        OnboardingOrchestrator().execute("mystore", self.CRAWL_URL)

        self.assertEqual(call_order, ["ocp", "integrate"])

    def test_propagates_failure_and_marks_onboarding_failed(self):
        self._make_onboarding("wpp-cloud")
        self.mock_payment_cls.return_value.execute.side_effect = RuntimeError("boom")

        with patch(
            "retail.projects.usecases.onboarding_orchestrator.mark_onboarding_failed"
        ) as mock_mark_failed, self.assertRaises(RuntimeError):
            OnboardingOrchestrator().execute("mystore", self.CRAWL_URL)

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
            OnboardingOrchestrator().execute("mystore", self.CRAWL_URL)

        self.assertIn("No channel configured", str(ctx.exception))
