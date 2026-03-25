from django.test import TestCase, override_settings
from unittest.mock import patch, MagicMock
from uuid import uuid4

from retail.api.vtex_projects.usecases.check_agent_active import (
    CheckAgentActiveUseCase,
    CACHE_TIMEOUT,
)
from retail.internal.test_mixins import TEST_SETTINGS_OVERRIDES


@override_settings(**TEST_SETTINGS_OVERRIDES)
class CheckAgentActiveUseCaseTest(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.use_case = CheckAgentActiveUseCase()
        self.vtex_account = "teststore"
        self.project = MagicMock()
        self.project.uuid = uuid4()

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedAgent.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_returns_true_when_abandoned_cart_agent_active(
        self, mock_settings, mock_project_qs, mock_ia_qs
    ):
        mock_settings.ABANDONED_CART_AGENT_UUID = "abc-123"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.return_value = True

        result = self.use_case.execute(self.vtex_account, "abandoned_cart")

        self.assertTrue(result)

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedAgent.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_returns_true_when_order_status_agent_active(
        self, mock_settings, mock_project_qs, mock_ia_qs
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "def-456"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.return_value = True

        result = self.use_case.execute(self.vtex_account, "order_status")

        self.assertTrue(result)

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedAgent.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_returns_true_for_custom_order_status_agent_with_parent(
        self, mock_settings, mock_project_qs, mock_ia_qs
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "def-456"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.side_effect = [False, True]

        result = self.use_case.execute(self.vtex_account, "order_status")

        self.assertTrue(result)

    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    def test_returns_false_when_project_not_found(self, mock_project_qs):
        from retail.projects.models import Project

        mock_project_qs.get.side_effect = Project.DoesNotExist

        result = self.use_case.execute(self.vtex_account, "abandoned_cart")

        self.assertFalse(result)

    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    def test_returns_false_when_multiple_projects(self, mock_project_qs):
        from retail.projects.models import Project

        mock_project_qs.get.side_effect = Project.MultipleObjectsReturned

        result = self.use_case.execute(self.vtex_account, "abandoned_cart")

        self.assertFalse(result)

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedFeature.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_returns_false_when_agent_uuid_not_configured_and_no_legacy(
        self, mock_settings, mock_project_qs, mock_if_qs
    ):
        mock_settings.ABANDONED_CART_AGENT_UUID = ""
        mock_project_qs.get.return_value = self.project
        mock_if_qs.filter.return_value.exists.return_value = False

        result = self.use_case.execute(self.vtex_account, "abandoned_cart")

        self.assertFalse(result)

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedFeature.objects"
    )
    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedAgent.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_returns_false_when_no_active_agent_and_no_legacy(
        self, mock_settings, mock_project_qs, mock_ia_qs, mock_if_qs
    ):
        mock_settings.ABANDONED_CART_AGENT_UUID = "abc-123"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.return_value = False
        mock_if_qs.filter.return_value.exists.return_value = False

        result = self.use_case.execute(self.vtex_account, "abandoned_cart")

        self.assertFalse(result)

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedFeature.objects"
    )
    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedAgent.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_returns_false_for_order_status_no_agent_no_legacy(
        self, mock_settings, mock_project_qs, mock_ia_qs, mock_if_qs
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "def-456"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.return_value = False
        mock_if_qs.filter.return_value.exists.return_value = False

        result = self.use_case.execute(self.vtex_account, "order_status")

        self.assertFalse(result)

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedFeature.objects"
    )
    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedAgent.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_returns_true_when_no_agent_but_legacy_feature_exists(
        self, mock_settings, mock_project_qs, mock_ia_qs, mock_if_qs
    ):
        mock_settings.ABANDONED_CART_AGENT_UUID = "abc-123"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.return_value = False
        mock_if_qs.filter.return_value.exists.return_value = True

        result = self.use_case.execute(self.vtex_account, "abandoned_cart")

        self.assertTrue(result)
        mock_if_qs.filter.assert_called_once_with(
            project=self.project,
            feature__code="abandoned_cart",
        )

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedFeature.objects"
    )
    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedAgent.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_returns_true_for_legacy_order_status_feature(
        self, mock_settings, mock_project_qs, mock_ia_qs, mock_if_qs
    ):
        mock_settings.ORDER_STATUS_AGENT_UUID = "def-456"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.return_value = False
        mock_if_qs.filter.return_value.exists.return_value = True

        result = self.use_case.execute(self.vtex_account, "order_status")

        self.assertTrue(result)
        mock_if_qs.filter.assert_called_once_with(
            project=self.project,
            feature__code="order_status",
        )

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedFeature.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_legacy_fallback_when_agent_uuid_not_configured(
        self, mock_settings, mock_project_qs, mock_if_qs
    ):
        mock_settings.ABANDONED_CART_AGENT_UUID = ""
        mock_project_qs.get.return_value = self.project
        mock_if_qs.filter.return_value.exists.return_value = True

        result = self.use_case.execute(self.vtex_account, "abandoned_cart")

        self.assertTrue(result)

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedAgent.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_skips_legacy_check_when_agent_found(
        self, mock_settings, mock_project_qs, mock_ia_qs
    ):
        mock_settings.ABANDONED_CART_AGENT_UUID = "abc-123"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.return_value = True

        result = self.use_case.execute(self.vtex_account, "abandoned_cart")

        self.assertTrue(result)

    @patch("retail.api.vtex_projects.usecases.check_agent_active.cache")
    def test_returns_cached_result_on_hit(self, mock_cache):
        mock_cache.get.return_value = True

        result = self.use_case.execute(self.vtex_account, "abandoned_cart")

        self.assertTrue(result)
        mock_cache.get.assert_called_once_with(
            f"agent_active_{self.vtex_account}_abandoned_cart"
        )

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedAgent.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.cache")
    def test_caches_result_with_correct_timeout(
        self, mock_cache, mock_settings, mock_project_qs, mock_ia_qs
    ):
        mock_cache.get.return_value = None
        mock_settings.ABANDONED_CART_AGENT_UUID = "abc-123"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.return_value = True

        self.use_case.execute(self.vtex_account, "abandoned_cart")

        mock_cache.set.assert_called_once_with(
            f"agent_active_{self.vtex_account}_abandoned_cart",
            True,
            timeout=CACHE_TIMEOUT,
        )

    @patch("retail.api.vtex_projects.usecases.check_agent_active.cache")
    def test_returns_cached_false_result(self, mock_cache):
        mock_cache.get.return_value = False

        result = self.use_case.execute(self.vtex_account, "abandoned_cart")

        self.assertFalse(result)
