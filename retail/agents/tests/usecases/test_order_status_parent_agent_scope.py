"""Custom order-status agents are resolved only from their own official parent."""

from unittest.mock import MagicMock
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.api.vtex_projects.usecases.check_agent_active import (
    CheckAgentActiveUseCase,
)
from retail.projects.models import Project

ORDER_STATUS_AGENT_UUID = uuid4()
OTHER_OFFICIAL_AGENT_UUID = uuid4()


@override_settings(
    ORDER_STATUS_AGENT_UUID=str(ORDER_STATUS_AGENT_UUID),
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "order-status-parent-agent-scope",
        }
    },
)
class OrderStatusParentAgentScopeTest(TestCase):
    def setUp(self):
        cache.clear()
        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Parent Scope Project",
            vtex_account="parent-scope-store",
        )
        self.cache_handler = MagicMock()
        self.cache_handler.get_role_agent.return_value = None
        self.usecase = AgentOrderStatusUpdateUsecase(cache_handler=self.cache_handler)
        self.check_agent_active = CheckAgentActiveUseCase()

    def tearDown(self):
        cache.clear()

    def _create_custom_child(
        self, parent_agent_uuid, *, is_active: bool = True
    ) -> IntegratedAgent:
        agent = Agent.objects.create(
            name="Custom agent",
            lambda_arn="arn:aws:lambda:custom",
            project=self.project,
            is_oficial=False,
            credentials={},
        )
        return IntegratedAgent.objects.create(
            agent=agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=is_active,
            parent_agent_uuid=parent_agent_uuid,
        )

    def test_resolves_custom_child_of_order_status(self):
        child = self._create_custom_child(ORDER_STATUS_AGENT_UUID)

        resolved = self.usecase.get_integrated_agent_if_exists(self.project)

        self.assertEqual(resolved.pk, child.pk)

    def test_ignores_custom_child_of_another_official_agent(self):
        self._create_custom_child(OTHER_OFFICIAL_AGENT_UUID)

        resolved = self.usecase.get_integrated_agent_if_exists(self.project)

        self.assertIsNone(resolved)

    def test_child_of_another_official_agent_does_not_cause_multiple_parents_error(
        self,
    ):
        order_status_child = self._create_custom_child(ORDER_STATUS_AGENT_UUID)
        self._create_custom_child(OTHER_OFFICIAL_AGENT_UUID)

        resolved = self.usecase.get_integrated_agent_if_exists(self.project)

        self.assertEqual(resolved.pk, order_status_child.pk)

    def test_two_active_children_of_order_status_still_raise(self):
        self._create_custom_child(ORDER_STATUS_AGENT_UUID)
        self._create_custom_child(ORDER_STATUS_AGENT_UUID)

        with self.assertRaises(ValidationError) as context:
            self.usecase.get_integrated_agent_if_exists(self.project)

        self.assertEqual(
            context.exception.detail["error"],
            "Only one custom child of the order-status agent "
            "is allowed for this project",
        )
        self.assertEqual(
            context.exception.detail["error"].code, "single_child_required"
        )

    def test_inactive_order_status_child_is_not_replaced_by_another_official_child(
        self,
    ):
        self._create_custom_child(ORDER_STATUS_AGENT_UUID, is_active=False)
        self._create_custom_child(OTHER_OFFICIAL_AGENT_UUID)

        resolved = self.usecase.get_integrated_agent_if_exists(self.project)

        self.assertIsNone(resolved)

    def test_check_agent_active_true_for_custom_child_of_order_status(self):
        self._create_custom_child(ORDER_STATUS_AGENT_UUID)

        self.assertTrue(
            self.check_agent_active.execute(self.project.vtex_account, "order_status")
        )

    def test_check_agent_active_false_for_custom_child_of_another_official_agent(
        self,
    ):
        self._create_custom_child(OTHER_OFFICIAL_AGENT_UUID)

        self.assertFalse(
            self.check_agent_active.execute(self.project.vtex_account, "order_status")
        )

    def test_check_agent_active_stays_true_when_another_official_child_coexists(self):
        self._create_custom_child(ORDER_STATUS_AGENT_UUID)
        self._create_custom_child(OTHER_OFFICIAL_AGENT_UUID)

        self.assertTrue(
            self.check_agent_active.execute(self.project.vtex_account, "order_status")
        )

    def test_check_agent_active_false_for_inactive_order_status_child(self):
        self._create_custom_child(ORDER_STATUS_AGENT_UUID, is_active=False)

        self.assertFalse(
            self.check_agent_active.execute(self.project.vtex_account, "order_status")
        )
