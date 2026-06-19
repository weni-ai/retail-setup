from django.test import TestCase, override_settings
from unittest.mock import patch, MagicMock

from retail.api.vtex_projects.usecases.check_onboarding_complete import (
    CheckOnboardingCompleteUseCase,
    CACHE_TIMEOUT,
    INACTIVE_STATUS,
)
from retail.internal.test_mixins import TEST_SETTINGS_OVERRIDES


@override_settings(**TEST_SETTINGS_OVERRIDES)
class CheckOnboardingCompleteUseCaseTest(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.use_case = CheckOnboardingCompleteUseCase()
        self.vtex_account = "teststore"

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    def _make_onboarding(self, completed=True):
        mock = MagicMock()
        mock.completed = completed
        return mock

    @patch(
        "retail.api.vtex_projects.usecases.check_onboarding_complete.ProjectOnboarding.objects"
    )
    def test_returns_complete_when_onboarding_finished(self, mock_qs):
        onboarding = self._make_onboarding(completed=True)
        mock_qs.get.return_value = onboarding

        result = self.use_case.execute(self.vtex_account)

        self.assertTrue(result.is_complete)
        self.assertIsNone(result.account_id)
        self.assertEqual(result.to_dict(), {"is_complete": True, "accountId": None})

    @patch(
        "retail.api.vtex_projects.usecases.check_onboarding_complete.ProjectOnboarding.objects"
    )
    def test_returns_incomplete_when_not_completed(self, mock_qs):
        onboarding = self._make_onboarding(completed=False)
        mock_qs.get.return_value = onboarding

        result = self.use_case.execute(self.vtex_account)

        self.assertFalse(result.is_complete)
        self.assertIsNone(result.account_id)

    @patch(
        "retail.api.vtex_projects.usecases.check_onboarding_complete.ProjectOnboarding.objects"
    )
    def test_returns_incomplete_when_onboarding_not_found(self, mock_qs):
        from retail.projects.models import ProjectOnboarding

        mock_qs.get.side_effect = ProjectOnboarding.DoesNotExist

        result = self.use_case.execute(self.vtex_account)

        self.assertFalse(result.is_complete)
        self.assertIsNone(result.account_id)

    @patch("retail.api.vtex_projects.usecases.check_onboarding_complete.cache")
    def test_returns_cached_result_on_hit(self, mock_cache):
        cached_result = MagicMock()
        cached_result.is_complete = True
        cached_result.account_id = None
        mock_cache.get.return_value = cached_result

        result = self.use_case.execute(self.vtex_account)

        self.assertEqual(result, cached_result)
        mock_cache.get.assert_called_once_with(
            f"onboarding_complete_{self.vtex_account}"
        )

    @patch(
        "retail.api.vtex_projects.usecases.check_onboarding_complete.ProjectOnboarding.objects"
    )
    @patch("retail.api.vtex_projects.usecases.check_onboarding_complete.cache")
    def test_caches_result_with_correct_timeout(self, mock_cache, mock_qs):
        mock_cache.get.return_value = None
        onboarding = self._make_onboarding(completed=True)
        mock_qs.get.return_value = onboarding

        result = self.use_case.execute(self.vtex_account)

        mock_cache.set.assert_called_once_with(
            f"onboarding_complete_{self.vtex_account}",
            result,
            timeout=CACHE_TIMEOUT,
        )

    @patch("retail.api.vtex_projects.usecases.check_onboarding_complete.cache")
    def test_returns_cached_inactive_status(self, mock_cache):
        mock_cache.get.return_value = INACTIVE_STATUS

        result = self.use_case.execute(self.vtex_account)

        self.assertFalse(result.is_complete)
        self.assertIsNone(result.account_id)

    def test_inactive_status_to_dict(self):
        self.assertEqual(
            INACTIVE_STATUS.to_dict(),
            {"is_complete": False, "accountId": None},
        )
