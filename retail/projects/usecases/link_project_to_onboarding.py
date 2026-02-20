import logging

from retail.projects.models import Project, ProjectOnboarding

logger = logging.getLogger(__name__)


class LinkProjectToOnboardingUseCase:
    """
    Links a newly created Project to an existing ProjectOnboarding
    identified by vtex_account.

    Called from the EDA consumer when a project creation event is received.
    Sets progress to 100%, which unblocks the wait task that triggers the crawl.
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
        onboarding.progress = 100
        onboarding.save(update_fields=["project", "current_step", "progress"])

        logger.info(
            f"Linked project={project.uuid} to onboarding={onboarding.uuid} "
            f"(vtex_account={project.vtex_account}, PROJECT_CONFIG=100%)"
        )
