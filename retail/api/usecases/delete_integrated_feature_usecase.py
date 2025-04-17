import logging

from typing import Dict, Optional

from rest_framework.exceptions import NotFound

from retail.features.integrated_feature_eda import IntegratedFeatureEDA
from retail.features.models import Feature, Project, IntegratedFeature
from retail.services.code_actions.service import CodeActionsService
from retail.clients.code_actions.client import CodeActionsClient


logger = logging.getLogger(__name__)


class DeleteIntegratedFeatureUseCase:
    """
    Use case responsible for deleting an IntegratedFeature and its associated Code Action.
    """

    def __init__(
        self, code_action_service: Optional[CodeActionsService] = None
    ) -> None:
        """
        Initializes the use case with the required services.

        Args:
            code_action_service (CodeActionsService, optional): Service to handle code action deletions.
        """
        self.code_action_service = code_action_service or CodeActionsService(
            CodeActionsClient()
        )

    def execute(self, project_uuid: str, feature_uuid: str, user_email: str) -> Dict:
        """
        Executes the deletion process of the integrated feature and its registered code action.

        Args:
            project_uuid (str): UUID of the project.
            feature_uuid (str): UUID of the feature.
            user_email (str): Email of the user requesting deletion.

        Returns:
            dict: A dictionary containing the deletion result or error.
        """
        # Get the integrated feature
        integrated_feature = self._get_integrated_feature(project_uuid, feature_uuid)

        # Delete code action
        code_action_result = self._delete_code_action(integrated_feature)
        if "error" in code_action_result:
            return code_action_result

        # Publish event and delete the integrated feature
        self._publish_removal_event(integrated_feature, user_email)
        integrated_feature.delete()

        logger.info(
            f"IntegratedFeature {integrated_feature.uuid} and code action deleted successfully."
        )
        return {
            "status": 200,
            "message": "Integrated feature and related code action successfully removed.",
        }

    def _get_integrated_feature(
        self, project_uuid: str, feature_uuid: str
    ) -> IntegratedFeature:
        """
        Retrieves the integrated feature for the given project and feature UUIDs.

        Args:
            project_uuid (str): UUID of the project.
            feature_uuid (str): UUID of the feature.

        Returns:
            IntegratedFeature: The integrated feature object.

        Raises:
            NotFound: If project, feature or integrated feature doesn't exist.
        """
        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            logger.warning(f"Project not found: {project_uuid}")
            raise NotFound(f"Project with UUID '{project_uuid}' does not exist.")

        try:
            feature = Feature.objects.get(uuid=feature_uuid)
        except Feature.DoesNotExist:
            logger.warning(f"Feature not found: {feature_uuid}")
            raise NotFound(f"Feature with UUID '{feature_uuid}' does not exist.")

        try:
            return IntegratedFeature.objects.get(project=project, feature=feature)
        except IntegratedFeature.DoesNotExist:
            logger.warning(
                f"Integrated feature not found: project={project_uuid}, feature={feature_uuid}"
            )
            raise NotFound(
                "Integrated feature does not exist for the given project and feature."
            )

    def _delete_code_action(self, integrated_feature: IntegratedFeature) -> Dict:
        """
        Deletes the code action associated with the integrated feature.

        Args:
            integrated_feature (IntegratedFeature): The integrated feature.

        Returns:
            dict: A dictionary containing the result or error.
        """
        try:
            # Extract the dictionary of registered actions and the project UUID
            action_data = integrated_feature.config.get("code_action_registered", {})

            self.code_action_service.delete_registered_code_action(action_data)
            logger.info(
                f"Code action for integrated feature {integrated_feature.uuid} deleted successfully."
            )
            return {"status": "success"}
        except Exception as e:
            logger.error(f"Failed to delete code action: {str(e)}")
            return {"status": 500, "error": "Failed to delete associated code action."}

    def _publish_removal_event(
        self, integrated_feature: IntegratedFeature, user_email: str
    ) -> None:
        """
        Publishes a message to notify that the integrated feature has been removed.

        Args:
            integrated_feature (IntegratedFeature): The removed feature.
            user_email (str): The user who triggered the removal.
        """
        body = {
            "project_uuid": str(integrated_feature.project.uuid),
            "feature_version": (
                str(integrated_feature.feature_version.uuid)
                if integrated_feature.feature_version
                else ""
            ),
            "feature_uuid": str(integrated_feature.feature.uuid),
            "user_email": user_email,
        }

        IntegratedFeatureEDA().publisher(body=body, exchange="removed-feature.topic")
        logger.info(f"Published removal event for feature {body['feature_uuid']}")
