from dataclasses import dataclass
from typing import Optional

from django.core.cache import cache

from retail.projects.usecases.agentic_cx_script import (
    CheckAgenticCxEligibilityUseCase,
    onboarding_complete_cache_key,
)

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
    """Checks whether the Agentic CX script should be active for a VTEX account.

    Used by the VTEX IO app-install event. The result is a capability
    check (channel, active agent, or completed onboarding), not the
    wizard ``completed`` flag alone.
    """

    def __init__(
        self,
        eligibility_use_case: Optional[CheckAgenticCxEligibilityUseCase] = None,
    ):
        self._eligibility_use_case = (
            eligibility_use_case or CheckAgenticCxEligibilityUseCase()
        )

    def execute(self, vtex_account: str) -> OnboardingStatus:
        cache_key = onboarding_complete_cache_key(vtex_account)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        result = self._check(vtex_account)
        cache.set(cache_key, result, timeout=CACHE_TIMEOUT)
        return result

    def _check(self, vtex_account: str) -> OnboardingStatus:
        if self._eligibility_use_case.execute(vtex_account):
            # accountId is reserved for the VTEX account ID that IO will
            # provide in the future
            return OnboardingStatus(is_complete=True, account_id=None)

        return INACTIVE_STATUS
