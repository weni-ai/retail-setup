import logging
from typing import Optional

from django.core.cache import cache
from django.utils import timezone

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.projects.models import Project, ProjectOnboarding
from retail.services.vtex_io.service import VtexIOService

logger = logging.getLogger(__name__)

ONBOARDING_COMPLETE_CACHE_KEY_PREFIX = "onboarding_complete_"


def onboarding_complete_cache_key(vtex_account: str) -> str:
    return f"{ONBOARDING_COMPLETE_CACHE_KEY_PREFIX}{vtex_account}"


class CheckAgenticCxEligibilityUseCase:
    """Decides whether the Agentic CX storefront script should be active.

    Eligibility is a capability check, not a wizard-completion check:
    the account needs the script as soon as it has a connected channel,
    an active integrated agent, or a completed onboarding.
    """

    def execute(self, vtex_account: str) -> bool:
        if not vtex_account:
            return False

        onboarding = self._get_onboarding(vtex_account)
        if onboarding is None:
            return False

        if onboarding.completed:
            return True

        if self._has_connected_channel(onboarding):
            return True

        return self._has_active_integrated_agent(onboarding)

    def _get_onboarding(self, vtex_account: str) -> Optional[ProjectOnboarding]:
        try:
            return ProjectOnboarding.objects.select_related("project").get(
                vtex_account=vtex_account
            )
        except ProjectOnboarding.DoesNotExist:
            logger.info(f"Onboarding not found for vtex_account={vtex_account}")
            return None

    @staticmethod
    def _has_connected_channel(onboarding: ProjectOnboarding) -> bool:
        channels = (onboarding.config or {}).get("channels") or {}
        return any(
            isinstance(channel_config, dict) and bool(channel_config.get("app_uuid"))
            for channel_config in channels.values()
        )

    @staticmethod
    def _has_active_integrated_agent(onboarding: ProjectOnboarding) -> bool:
        if onboarding.project_id is None:
            return False

        return IntegratedAgent.objects.filter(
            project_id=onboarding.project_id,
            is_active=True,
        ).exists()


class EnsureAgenticCxScriptActiveUseCase:
    """Idempotently activates the Agentic CX script on the VTEX IO app."""

    def __init__(
        self,
        vtex_io_service: Optional[VtexIOService] = None,
        eligibility_use_case: Optional[CheckAgenticCxEligibilityUseCase] = None,
    ):
        self._vtex_io_service = vtex_io_service or VtexIOService()
        self._eligibility_use_case = (
            eligibility_use_case or CheckAgenticCxEligibilityUseCase()
        )

    def execute(self, vtex_account: str) -> None:
        if not vtex_account:
            logger.warning("Skipping Agentic CX script activation: empty vtex_account")
            return

        project = self._get_project(vtex_account)
        if self._is_already_active(project):
            logger.info(
                f"Agentic CX script already marked active for "
                f"vtex_account={vtex_account}"
            )
            return

        if not self._eligibility_use_case.execute(vtex_account):
            logger.info(
                f"Account is not eligible for Agentic CX script "
                f"activation: vtex_account={vtex_account}"
            )
            return

        self._vtex_io_service.activate_agentic_cx_script(
            account_domain=f"{vtex_account}.myvtex.com",
            vtex_account=vtex_account,
        )
        self._persist_active_marker(project, vtex_account)
        cache.delete(onboarding_complete_cache_key(vtex_account))

        logger.info(f"Agentic CX script activated for vtex_account={vtex_account}")

    def _get_project(self, vtex_account: str) -> Optional[Project]:
        try:
            return Project.objects.get(vtex_account=vtex_account)
        except Project.DoesNotExist:
            return None

    @staticmethod
    def _is_already_active(project: Optional[Project]) -> bool:
        if project is None:
            return False
        marker = (project.config or {}).get("agentic_cx_script") or {}
        return marker.get("active") is True

    def _persist_active_marker(
        self, project: Optional[Project], vtex_account: str
    ) -> None:
        if project is None:
            logger.warning(
                f"No project found for vtex_account={vtex_account}; "
                f"script was activated without a local marker"
            )
            return

        config = dict(project.config or {})
        config["agentic_cx_script"] = {
            "active": True,
            "activated_at": timezone.now().isoformat(),
        }
        project.config = config
        project.save(update_fields=["config"])
        project.clear_cache()
