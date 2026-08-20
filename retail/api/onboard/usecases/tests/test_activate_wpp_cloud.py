from uuid import uuid4
from unittest.mock import patch

from django.test import TestCase, override_settings

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.api.onboard.usecases.activate_wpp_cloud import ActivateWppCloudUseCase
from retail.api.onboard.usecases.dto import ActivateWppCloudDTO
from retail.projects.models import Project


FAKE_AGENT_UUID = str(uuid4())


@override_settings(ABANDONED_CART_AGENT_UUID=FAKE_AGENT_UUID)
class TestActivateWppCloudUseCase(TestCase):
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

    def test_sets_contact_percentage(self):
        dto = ActivateWppCloudDTO(
            project_uuid=str(self.project.uuid),
            percentage=10,
        )

        result = self.use_case.execute(dto)

        self.integrated_agent.refresh_from_db()
        self.assertEqual(result.contact_percentage, 10)
        self.assertEqual(self.integrated_agent.contact_percentage, 10)
        self.mock_task.delay.assert_called_once_with("mystore")

    def test_sets_percentage_to_zero(self):
        self.integrated_agent.contact_percentage = 50
        self.integrated_agent.save()

        dto = ActivateWppCloudDTO(
            project_uuid=str(self.project.uuid),
            percentage=0,
        )

        result = self.use_case.execute(dto)

        self.integrated_agent.refresh_from_db()
        self.assertEqual(result.contact_percentage, 0)

    def test_raises_not_found_when_no_integrated_agent(self):
        self.integrated_agent.delete()

        dto = ActivateWppCloudDTO(
            project_uuid=str(self.project.uuid),
            percentage=10,
        )

        with self.assertRaises(NotFound):
            self.use_case.execute(dto)

        self.mock_task.delay.assert_not_called()

    def test_raises_not_found_when_agent_inactive(self):
        self.integrated_agent.is_active = False
        self.integrated_agent.save()

        dto = ActivateWppCloudDTO(
            project_uuid=str(self.project.uuid),
            percentage=10,
        )

        with self.assertRaises(NotFound):
            self.use_case.execute(dto)

        self.mock_task.delay.assert_not_called()

    @override_settings(ABANDONED_CART_AGENT_UUID="")
    def test_raises_validation_error_when_uuid_not_configured(self):
        dto = ActivateWppCloudDTO(
            project_uuid=str(self.project.uuid),
            percentage=10,
        )

        with self.assertRaises(ValidationError):
            self.use_case.execute(dto)
