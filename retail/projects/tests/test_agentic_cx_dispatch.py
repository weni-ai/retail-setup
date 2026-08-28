from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.exceptions import APIException, NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.api.onboard.usecases.activate_wpp_cloud import ActivateWppCloudUseCase
from retail.api.onboard.usecases.dto import ActivateWebchatDTO, ActivateWppCloudDTO
from retail.api.onboard.usecases.publish_webchat_script import (
    PublishWebchatScriptUseCase,
)
from retail.api.vtex_projects.usecases.check_onboarding_complete import (
    CheckOnboardingCompleteUseCase,
    CACHE_TIMEOUT,
    INACTIVE_STATUS,
)
from retail.internal.test_mixins import TEST_SETTINGS_OVERRIDES
from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.agentic_cx_script import onboarding_complete_cache_key
from retail.services.webchat_push.service import WebchatPublishError


FAKE_AGENT_UUID = str(uuid4())


class TestPublishWebchatScriptDispatchesAgenticCx(TestCase):
    def setUp(self):
        self._task_patcher = patch(
            "retail.api.onboard.usecases.publish_webchat_script.task_ensure_agentic_cx_script_active"
        )
        self.mock_task = self._task_patcher.start()
        self.addCleanup(self._task_patcher.stop)

        self.integrations_service = MagicMock()
        self.webchat_push_service = MagicMock()
        self.usecase = PublishWebchatScriptUseCase(
            integrations_service=self.integrations_service,
            webchat_push_service=self.webchat_push_service,
        )
        self.dto = ActivateWebchatDTO(
            app_uuid="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            account_id="b1165658e9e54790881952eb99341e51",
            vtex_account="mystore",
        )

    def test_dispatches_task_after_successful_publish(self):
        self.integrations_service.get_channel_app.return_value = {
            "config": {"script": "https://example.com/wwc.js"}
        }
        self.webchat_push_service.publish_webchat_script.return_value = [
            "https://bucket.s3.amazonaws.com/webchat.js"
        ]

        result = self.usecase.execute(self.dto)

        self.mock_task.delay.assert_called_once_with("mystore")
        self.assertEqual(
            result.to_dict(),
            {"script_urls": ["https://bucket.s3.amazonaws.com/webchat.js"]},
        )

    def test_does_not_dispatch_when_publish_fails(self):
        self.integrations_service.get_channel_app.return_value = {
            "config": {"script": "https://example.com/wwc.js"}
        }
        self.webchat_push_service.publish_webchat_script.side_effect = (
            WebchatPublishError("S3 error")
        )

        with self.assertRaises(APIException):
            self.usecase.execute(self.dto)

        self.mock_task.delay.assert_not_called()

    def test_does_not_dispatch_when_app_has_no_script(self):
        self.integrations_service.get_channel_app.return_value = {"config": {}}

        with self.assertRaises(ValidationError):
            self.usecase.execute(self.dto)

        self.mock_task.delay.assert_not_called()


@override_settings(ABANDONED_CART_AGENT_UUID=FAKE_AGENT_UUID)
class TestActivateWppCloudDispatchesAgenticCx(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.agent = Agent.objects.create(
            uuid=FAKE_AGENT_UUID,
            name="Abandoned Cart",
            slug="abandoned-cart",
            is_oficial=True,
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            is_active=True,
            contact_percentage=0,
        )
        self._task_patcher = patch(
            "retail.api.onboard.usecases.activate_wpp_cloud.task_ensure_agentic_cx_script_active"
        )
        self.mock_task = self._task_patcher.start()
        self.addCleanup(self._task_patcher.stop)
        self.use_case = ActivateWppCloudUseCase()

    def test_dispatches_task_after_activating_agent(self):
        dto = ActivateWppCloudDTO(
            project_uuid=str(self.project.uuid),
            percentage=10,
        )

        self.use_case.execute(dto)

        self.mock_task.delay.assert_called_once_with("mystore")

    def test_does_not_dispatch_when_project_has_no_vtex_account(self):
        self.project.vtex_account = ""
        self.project.save(update_fields=["vtex_account"])

        dto = ActivateWppCloudDTO(
            project_uuid=str(self.project.uuid),
            percentage=10,
        )

        self.use_case.execute(dto)

        self.mock_task.delay.assert_not_called()

    def test_does_not_dispatch_when_integrated_agent_is_missing(self):
        self.integrated_agent.delete()
        dto = ActivateWppCloudDTO(
            project_uuid=str(self.project.uuid),
            percentage=10,
        )

        with self.assertRaises(NotFound):
            self.use_case.execute(dto)

        self.mock_task.delay.assert_not_called()


@override_settings(**TEST_SETTINGS_OVERRIDES)
class TestCheckOnboardingCompleteUsesEligibility(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.mock_eligibility = MagicMock()
        self.use_case = CheckOnboardingCompleteUseCase(
            eligibility_use_case=self.mock_eligibility
        )
        self.vtex_account = "teststore"

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    def test_returns_complete_when_eligible(self):
        self.mock_eligibility.execute.return_value = True

        result = self.use_case.execute(self.vtex_account)

        self.assertTrue(result.is_complete)
        self.assertIsNone(result.account_id)
        self.mock_eligibility.execute.assert_called_once_with(self.vtex_account)

    def test_returns_incomplete_when_not_eligible(self):
        self.mock_eligibility.execute.return_value = False

        result = self.use_case.execute(self.vtex_account)

        self.assertFalse(result.is_complete)

    def test_inactive_status_to_dict(self):
        self.assertEqual(
            INACTIVE_STATUS.to_dict(),
            {"is_complete": False, "accountId": None},
        )

    @patch("retail.api.vtex_projects.usecases.check_onboarding_complete.cache")
    def test_returns_cached_result_on_hit(self, mock_cache):
        cached_result = MagicMock()
        mock_cache.get.return_value = cached_result

        result = self.use_case.execute(self.vtex_account)

        self.assertEqual(result, cached_result)
        self.mock_eligibility.execute.assert_not_called()

    @patch("retail.api.vtex_projects.usecases.check_onboarding_complete.cache")
    def test_caches_result_with_correct_timeout(self, mock_cache):
        mock_cache.get.return_value = None
        self.mock_eligibility.execute.return_value = True

        result = self.use_case.execute(self.vtex_account)

        mock_cache.set.assert_called_once_with(
            onboarding_complete_cache_key(self.vtex_account),
            result,
            timeout=CACHE_TIMEOUT,
        )

    def test_default_constructor_uses_shared_eligibility_rule(self):
        with patch(
            "retail.projects.agentic_cx_tasks.task_ensure_agentic_cx_script_active"
        ):
            project = Project.objects.create(
                name="Test", uuid=uuid4(), vtex_account=self.vtex_account
            )
            ProjectOnboarding.objects.create(
                vtex_account=self.vtex_account,
                project=project,
                completed=True,
            )

        result = CheckOnboardingCompleteUseCase().execute(self.vtex_account)

        self.assertTrue(result.is_complete)
