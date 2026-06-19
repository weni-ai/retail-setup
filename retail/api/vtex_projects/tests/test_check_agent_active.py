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
    def test_returns_true_when_payment_recovery_agent_active(
        self, mock_settings, mock_project_qs, mock_ia_qs
    ):
        mock_settings.PAYMENT_RECOVERY_AGENT_UUID = "ghi-789"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.return_value = True

        result = self.use_case.execute(self.vtex_account, "payment_recovery")

        self.assertTrue(result)
        mock_ia_qs.filter.assert_called_once_with(
            agent__uuid="ghi-789",
            project=self.project,
            is_active=True,
        )

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedFeature.objects"
    )
    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedAgent.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_returns_false_for_payment_recovery_no_agent_no_legacy(
        self, mock_settings, mock_project_qs, mock_ia_qs, mock_if_qs
    ):
        mock_settings.PAYMENT_RECOVERY_AGENT_UUID = "ghi-789"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.return_value = False
        mock_if_qs.filter.return_value.exists.return_value = False

        result = self.use_case.execute(self.vtex_account, "payment_recovery")

        self.assertFalse(result)

    @patch(
        "retail.api.vtex_projects.usecases.check_agent_active.IntegratedAgent.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_agent_active.Project.objects")
    @patch("retail.api.vtex_projects.usecases.check_agent_active.settings")
    def test_payment_recovery_does_not_check_parent_agent_fallback(
        self, mock_settings, mock_project_qs, mock_ia_qs
    ):
        """``parent_agent_uuid`` fallback is exclusive to ``order_status``.

        Payment recovery has no inheritance model, so the use case must
        not query ``parent_agent_uuid__isnull=False`` for it.
        """
        mock_settings.PAYMENT_RECOVERY_AGENT_UUID = "ghi-789"
        mock_project_qs.get.return_value = self.project
        mock_ia_qs.filter.return_value.exists.return_value = False

        self.use_case.execute(self.vtex_account, "payment_recovery")

        mock_ia_qs.filter.assert_called_once_with(
            agent__uuid="ghi-789",
            project=self.project,
            is_active=True,
        )

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


@override_settings(**TEST_SETTINGS_OVERRIDES)
class CheckAgentActiveUseCaseExecuteAnyTest(TestCase):
    """Covers the OR-semantics variant used by callers that need to ask
    about multiple agent roles in a single round-trip."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.use_case = CheckAgentActiveUseCase()
        self.vtex_account = "teststore"

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    def test_returns_true_when_first_agent_is_active(self):
        with patch.object(
            self.use_case, "execute", side_effect=[True, False]
        ) as mock_execute:
            result = self.use_case.execute_any(
                self.vtex_account, ["order_status", "payment_recovery"]
            )

        self.assertTrue(result)
        mock_execute.assert_called_once_with(self.vtex_account, "order_status")

    def test_returns_true_when_only_second_agent_is_active(self):
        with patch.object(
            self.use_case, "execute", side_effect=[False, True]
        ) as mock_execute:
            result = self.use_case.execute_any(
                self.vtex_account, ["order_status", "payment_recovery"]
            )

        self.assertTrue(result)
        self.assertEqual(mock_execute.call_count, 2)

    def test_returns_false_when_no_agent_is_active(self):
        with patch.object(
            self.use_case, "execute", side_effect=[False, False]
        ) as mock_execute:
            result = self.use_case.execute_any(
                self.vtex_account, ["order_status", "payment_recovery"]
            )

        self.assertFalse(result)
        self.assertEqual(mock_execute.call_count, 2)

    def test_returns_false_for_empty_list(self):
        with patch.object(self.use_case, "execute") as mock_execute:
            result = self.use_case.execute_any(self.vtex_account, [])

        self.assertFalse(result)
        mock_execute.assert_not_called()

    def test_short_circuits_on_first_truthy_result(self):
        """``execute_any`` must not query downstream agents once a match
        is found — this keeps the cache footprint and DB load minimal
        for the agentic-cx hot path."""
        with patch.object(
            self.use_case, "execute", side_effect=[True, Exception("must not run")]
        ) as mock_execute:
            result = self.use_case.execute_any(
                self.vtex_account,
                ["order_status", "payment_recovery"],
            )

        self.assertTrue(result)
        mock_execute.assert_called_once_with(self.vtex_account, "order_status")
