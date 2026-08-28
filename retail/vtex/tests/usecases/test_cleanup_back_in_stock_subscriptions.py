import uuid
from unittest.mock import MagicMock

from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project
from retail.vtex.usecases.cleanup_back_in_stock_subscriptions import (
    CleanupBackInStockSubscriptionsUseCase,
)


BACK_IN_STOCK_AGENT_UUID = str(uuid.uuid4())


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "cleanup-back-in-stock-subscriptions-tests",
        }
    },
    BACK_IN_STOCK_AGENT_UUID=BACK_IN_STOCK_AGENT_UUID,
)
class CleanupBackInStockSubscriptionsUseCaseTest(TestCase):
    def setUp(self):
        self.mock_service = MagicMock()
        self.use_case = CleanupBackInStockSubscriptionsUseCase(
            vtex_io_service=self.mock_service
        )
        self.project_a = Project.objects.create(
            uuid="11111111-1111-1111-1111-111111111111",
            name="Store A",
            vtex_account="storea",
        )
        self.project_b = Project.objects.create(
            uuid="22222222-2222-2222-2222-222222222222",
            name="Store B",
            vtex_account="storeb",
        )
        Project.objects.create(
            uuid="33333333-3333-3333-3333-333333333333",
            name="No account",
            vtex_account="",
        )
        self.agent = Agent.objects.create(
            uuid=BACK_IN_STOCK_AGENT_UUID,
            name="Back in stock",
            slug="back_in_stock",
            description="Back in stock agent",
            project=self.project_a,
        )
        self._activate_agent(self.project_a)
        self._activate_agent(self.project_b)

    def _activate_agent(self, project: Project, is_active: bool = True) -> None:
        IntegratedAgent.objects.create(
            uuid=uuid.uuid4(),
            agent=self.agent,
            project=project,
            is_active=is_active,
        )

    def test_posts_cleanup_only_for_accounts_with_active_agent(self):
        self.mock_service.cleanup_availability_notify.return_value = {
            "deleted": 2,
            "scanned": 10,
            "skipped": False,
        }

        self.use_case.execute()

        self.mock_service.cleanup_availability_notify.assert_any_call(
            account_domain="storea.myvtex.com",
            vtex_account="storea",
        )
        self.mock_service.cleanup_availability_notify.assert_any_call(
            account_domain="storeb.myvtex.com",
            vtex_account="storeb",
        )
        self.assertEqual(self.mock_service.cleanup_availability_notify.call_count, 2)

    def test_skips_account_when_agent_is_inactive(self):
        IntegratedAgent.objects.filter(project=self.project_b).update(is_active=False)
        self.mock_service.cleanup_availability_notify.return_value = {
            "deleted": 1,
            "scanned": 3,
            "skipped": False,
        }

        self.use_case.execute()

        self.mock_service.cleanup_availability_notify.assert_called_once_with(
            account_domain="storea.myvtex.com",
            vtex_account="storea",
        )

    def test_skips_account_without_back_in_stock_agent(self):
        IntegratedAgent.objects.filter(project=self.project_b).delete()
        self.mock_service.cleanup_availability_notify.return_value = {
            "deleted": 1,
            "scanned": 3,
            "skipped": False,
        }

        self.use_case.execute()

        self.mock_service.cleanup_availability_notify.assert_called_once_with(
            account_domain="storea.myvtex.com",
            vtex_account="storea",
        )

    def test_logs_io_response_without_aggregating_deleted(self):
        io_response = {"deleted": 2, "scanned": 10, "skipped": False}
        self.mock_service.cleanup_availability_notify.return_value = io_response
        IntegratedAgent.objects.filter(project=self.project_b).delete()

        with self.assertLogs(
            "retail.vtex.usecases.cleanup_back_in_stock_subscriptions",
            level="INFO",
        ) as logs:
            self.use_case.execute()

        combined = " ".join(logs.output)
        self.assertIn("response=", combined)
        self.assertIn("deleted", combined)
        self.assertIn("2", combined)

    def test_continues_when_one_account_fails(self):
        def _cleanup(account_domain, vtex_account):
            if vtex_account == "storea":
                return None
            return {"deleted": 1, "scanned": 3, "skipped": False}

        self.mock_service.cleanup_availability_notify.side_effect = _cleanup

        self.use_case.execute()

        self.assertEqual(self.mock_service.cleanup_availability_notify.call_count, 2)

    def test_does_not_call_io_when_agent_uuid_is_not_configured(self):
        with self.settings(BACK_IN_STOCK_AGENT_UUID=""):
            self.use_case.execute()

        self.mock_service.cleanup_availability_notify.assert_not_called()
