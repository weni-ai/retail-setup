import logging

logger = logging.getLogger(__name__)


class TrialSuspensionService:
    """Placeholder for the remote trial suspension flow on Connect.

    The real implementation lives on the `feature/suspend-trial-project`
    branch (SuspendTrialProjectUseCase + SuspendTrialProjectDTO) and is
    not merged into main yet. Until that merge happens, this service
    only logs the intent and the local block alone is responsible for
    stopping further broadcasts.

    TODO(suspend-trial-merge): once `feature/suspend-trial-project` is
    merged, wire this service to the real flow:

        from retail.projects.usecases.suspend_trial_dto import (
            SuspendTrialProjectDTO,
        )
        from retail.projects.usecases.suspend_trial_project import (
            SuspendTrialProjectUseCase,
        )

        def suspend(self, project_uuid: str, limit: int) -> None:
            SuspendTrialProjectUseCase().execute(
                SuspendTrialProjectDTO(
                    project_uuid=project_uuid,
                    conversation_limit=limit,
                )
            )
    """

    def suspend(self, project_uuid: str, limit: int) -> None:
        logger.warning(
            f"[BROADCAST_TRACKING] suspension_placeholder: "
            f"project_uuid={project_uuid} broadcast_limit={limit} "
            f"local_block=applied remote_connect_suspension=not_implemented "
            f"reason=pending_feature_suspend_trial_project_merge"
        )
