import logging

from retail.projects.models import Project, ProjectOnboarding

logger = logging.getLogger(__name__)


PROJECT_LINKED_PROGRESS = 30


class LinkProjectToOnboardingUseCase:
    """
    Links a newly created Project to an existing ProjectOnboarding
    identified by vtex_account.

    Called from the EDA consumer when a project creation event is received.
    Sets ``current_step = "PROJECT_CONFIG"`` and a partial progress
    (``PROJECT_LINKED_PROGRESS``) so the pre-crawl channel setup task
    can drive progress the rest of the way to 100% before transitioning
    to CRAWL.
    """

    @staticmethod
    def execute(project: Project) -> None:
        """
        Searches for a pending onboarding by vtex_account and links it
        to the given project.

        Args:
            project: The newly created/updated Project instance.
        """
        if not project.vtex_account:
            return

        try:
            onboarding = ProjectOnboarding.objects.get(
                vtex_account=project.vtex_account,
                project__isnull=True,
            )
        except ProjectOnboarding.DoesNotExist:
            logger.info(
                f"No pending onboarding found for vtex_account={project.vtex_account}"
            )
            return

        onboarding.project = project
        onboarding.current_step = "PROJECT_CONFIG"
        onboarding.progress = PROJECT_LINKED_PROGRESS
        onboarding.save(update_fields=["project", "current_step", "progress"])

        logger.info(
            f"Linked project={project.uuid} to onboarding={onboarding.uuid} "
            f"(vtex_account={project.vtex_account}, "
            f"PROJECT_CONFIG={PROJECT_LINKED_PROGRESS}%)"
        )
