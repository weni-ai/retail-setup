import logging

from dataclasses import dataclass
from typing import Optional

from django.core.cache import cache

from retail.projects.models import ProjectOnboarding


logger = logging.getLogger(__name__)

CACHE_TIMEOUT = 60


@dataclass(frozen=True)
class OnboardingStatus:
    is_complete: bool
    account_id: Optional[int]

    def to_dict(self) -> dict:
        return {
            "is_complete": self.is_complete,
            "accountId": self.account_id,
        }


INACTIVE_STATUS = OnboardingStatus(is_complete=False, account_id=None)


class CheckOnboardingCompleteUseCase:
    """Checks whether the onboarding process is fully completed for a VTEX account."""

    def execute(self, vtex_account: str) -> OnboardingStatus:
        cache_key = f"onboarding_complete_{vtex_account}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        result = self._check(vtex_account)
        cache.set(cache_key, result, timeout=CACHE_TIMEOUT)
        return result

    def _check(self, vtex_account: str) -> OnboardingStatus:
        onboarding = self._get_onboarding(vtex_account)
        if not onboarding:
            return INACTIVE_STATUS

        if not onboarding.completed:
            return INACTIVE_STATUS

        # accountId is reserved for the VTEX account ID that IO will provide in the future
        return OnboardingStatus(is_complete=True, account_id=None)

    def _get_onboarding(self, vtex_account: str) -> Optional[ProjectOnboarding]:
        try:
            return ProjectOnboarding.objects.get(vtex_account=vtex_account)
        except ProjectOnboarding.DoesNotExist:
            logger.info(f"Onboarding not found for vtex_account={vtex_account}")
            return None
