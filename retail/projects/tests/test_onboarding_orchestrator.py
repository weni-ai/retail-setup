from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.onboarding_orchestrator import (
    NEXUS_CONFIG_START_PROGRESS,
    OnboardingOrchestrator,
)


class TestOnboardingOrchestrator(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            current_step="CRAWL",
            progress=100,
            crawler_result=ProjectOnboarding.SUCCESS,
            config={
                "channels": {
                    "wwc": {
                        "app_uuid": str(uuid4()),
                    }
                }
            },
        )

    @patch("retail.projects.usecases.onboarding_orchestrator.IntegrateAgentsUseCase")
    @patch(
        "retail.projects.usecases.onboarding_orchestrator.ConfigureAgentBuilderUseCase"
    )
    def test_runs_agent_builder_then_integrate(
        self, mock_agent_builder_cls, mock_integrate_cls
    ):
        mock_agent_builder = MagicMock()
        mock_agent_builder_cls.return_value = mock_agent_builder
        mock_integrate = MagicMock()
        mock_integrate_cls.return_value = mock_integrate

        contents = [{"link": "a", "title": "b", "content": "c"}]
        OnboardingOrchestrator().execute("mystore", contents)

        mock_agent_builder.execute.assert_called_once_with("mystore", contents)
        mock_integrate.execute.assert_called_once_with("mystore")

    @patch("retail.projects.usecases.onboarding_orchestrator.IntegrateAgentsUseCase")
    @patch(
        "retail.projects.usecases.onboarding_orchestrator.ConfigureAgentBuilderUseCase"
    )
    def test_transitions_to_nexus_config_step(
        self, mock_agent_builder_cls, _mock_integrate_cls
    ):
        """The orchestrator must mark NEXUS_CONFIG so the UI advances."""
        progress_at_agent_time = {}

        def capture(vtex_account, _contents):
            onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
            progress_at_agent_time["step"] = onboarding.current_step
            progress_at_agent_time["progress"] = onboarding.progress

        mock_agent_builder = MagicMock()
        mock_agent_builder.execute.side_effect = capture
        mock_agent_builder_cls.return_value = mock_agent_builder

        OnboardingOrchestrator().execute("mystore", [])

        self.assertEqual(progress_at_agent_time["step"], "NEXUS_CONFIG")
        self.assertEqual(
            progress_at_agent_time["progress"], NEXUS_CONFIG_START_PROGRESS
        )

    @patch("retail.projects.usecases.onboarding_orchestrator.mark_onboarding_failed")
    @patch("retail.projects.usecases.onboarding_orchestrator.IntegrateAgentsUseCase")
    @patch(
        "retail.projects.usecases.onboarding_orchestrator.ConfigureAgentBuilderUseCase"
    )
    def test_marks_failed_when_agent_builder_fails(
        self,
        mock_agent_builder_cls,
        mock_integrate_cls,
        mock_mark_failed,
    ):
        mock_agent_builder = MagicMock()
        mock_agent_builder.execute.side_effect = RuntimeError("nexus down")
        mock_agent_builder_cls.return_value = mock_agent_builder

        mock_integrate = MagicMock()
        mock_integrate_cls.return_value = mock_integrate

        with self.assertRaises(RuntimeError):
            OnboardingOrchestrator().execute("mystore", [])

        mock_mark_failed.assert_called_once()
        mock_integrate.execute.assert_not_called()

    @patch("retail.projects.usecases.onboarding_orchestrator.mark_onboarding_failed")
    @patch("retail.projects.usecases.onboarding_orchestrator.IntegrateAgentsUseCase")
    @patch(
        "retail.projects.usecases.onboarding_orchestrator.ConfigureAgentBuilderUseCase"
    )
    def test_marks_failed_when_integrate_fails(
        self,
        mock_agent_builder_cls,
        mock_integrate_cls,
        mock_mark_failed,
    ):
        mock_agent_builder = MagicMock()
        mock_agent_builder_cls.return_value = mock_agent_builder

        mock_integrate = MagicMock()
        mock_integrate.execute.side_effect = RuntimeError("nexus error")
        mock_integrate_cls.return_value = mock_integrate

        with self.assertRaises(RuntimeError):
            OnboardingOrchestrator().execute("mystore", [])

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
