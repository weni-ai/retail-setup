from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.content_base_progress_helpers import (
    compute_overall_percent,
)

_TERMINAL_CRAWLER_RESULTS = (
    ProjectOnboarding.SUCCESS,
    ProjectOnboarding.FAIL,
)


class GetContentBaseProgressUseCase:
    def execute(self, vtex_account: str) -> int:
        onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
        snapshot = (onboarding.config or {}).get("content_base_progress") or {}
        if self._legacy_crawl_already_finished(onboarding, snapshot):
            return 100
        return compute_overall_percent(snapshot)

    @staticmethod
    def _legacy_crawl_already_finished(
        onboarding: ProjectOnboarding, snapshot: dict
    ) -> bool:
        """
        Onboardings finished before content_base_progress existed have a
        terminal crawler_result and no snapshot. The crawl is not in flight,
        so clients should see 100% instead of staying blocked at 0%.
        """
        return (
            not snapshot and onboarding.crawler_result in _TERMINAL_CRAWLER_RESULTS
        )
