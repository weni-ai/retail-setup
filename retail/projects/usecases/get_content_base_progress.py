from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.content_base_progress_helpers import (
    compute_overall_percent,
)


class GetContentBaseProgressUseCase:
    def execute(self, vtex_account: str) -> int:
        onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
        snapshot = (onboarding.config or {}).get("content_base_progress") or {}
        return compute_overall_percent(snapshot)
