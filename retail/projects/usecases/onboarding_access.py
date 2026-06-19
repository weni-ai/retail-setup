import logging

from retail.projects.models import Project, ProjectOnboarding

logger = logging.getLogger(__name__)


def get_or_create_active_onboarding(
    vtex_account: str,
) -> tuple[ProjectOnboarding, bool]:
    """
    Returns the active onboarding for a VTEX account.

    Inactive records are never reactivated automatically — a new active row
    is created instead so stale channel UUIDs and config are not reused.
    """
    try:
        return ProjectOnboarding.objects.get(vtex_account=vtex_account), False
    except ProjectOnboarding.DoesNotExist:
        if ProjectOnboarding.all_objects.filter(
            vtex_account=vtex_account,
            is_active=False,
        ).exists():
            logger.warning(
                f"Inactive onboarding exists for vtex_account={vtex_account}; "
                "creating a new active record"
            )

        onboarding = ProjectOnboarding.objects.create(vtex_account=vtex_account)
        return onboarding, True


def onboarding_linked_to_active_project_record(
    onboarding: ProjectOnboarding,
) -> bool:
    """True when project_id points to an active Project row."""
    if not onboarding.project_id:
        return False
    return Project.objects.filter(pk=onboarding.project_id).exists()


def deactivate_onboardings_for_project(project: Project) -> int:
    """Soft-deletes every onboarding linked to the given project."""
    return ProjectOnboarding.all_objects.filter(project_id=project.id).update(
        is_active=False
    )
