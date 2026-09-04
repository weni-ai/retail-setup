from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from retail.api.vtex_projects.usecases.check_onboarding_complete import (
    CheckOnboardingCompleteUseCase,
    CACHE_TIMEOUT,
    INACTIVE_STATUS,
)
from retail.internal.test_mixins import TEST_SETTINGS_OVERRIDES
from retail.projects.usecases.agentic_cx_script import onboarding_complete_cache_key


@override_settings(**TEST_SETTINGS_OVERRIDES)
class CheckOnboardingCompleteUseCaseTest(TestCase):
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
        self.assertEqual(result.to_dict(), {"is_complete": True, "accountId": None})
        self.mock_eligibility.execute.assert_called_once_with(self.vtex_account)

    def test_returns_incomplete_when_not_eligible(self):
        self.mock_eligibility.execute.return_value = False

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
            onboarding_complete_cache_key(self.vtex_account)
        )
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
