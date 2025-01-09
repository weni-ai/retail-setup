from rest_framework.exceptions import ValidationError, NotFound
from django.conf import settings

from retail.api.integrated_feature.serializers import IntegratedFeatureSerializer
from retail.api.usecases.install_actions_usecase import InstallActions
from retail.api.usecases.populate_globals_values import PopulateGlobalsValuesUsecase
from retail.api.usecases.populate_globals_with_defaults import PopulateDefaultsUseCase

from retail.features.integrated_feature_eda import IntegratedFeatureEDA

from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project


class CreateIntegratedFeatureUseCase:
    """
    Use case to handle the creation and configuration of an IntegratedFeature.
    """

    def __init__(self, integrations_service, flows_service, install_actions=None):
        self.integrations_service = integrations_service
        self.flows_service = flows_service

        self.install_actions = install_actions or InstallActions()

    def execute(self, request_data, user):
        """
        Execute the use case to create and configure an IntegratedFeature.

        Args:
            request_data (dict): Data from the request.
            user (User): The user performing the action.

        Returns:
            dict: Response data including integration details.

        Raises:
            ValidationError: If the feature is already integrated with the project.
            NotFound: If the feature or project does not exist.
        """
        # Validation and object retrieval
        feature = self._get_feature(request_data["feature_uuid"])
        project = self._get_project(request_data["project_uuid"])

        # Check if the feature is already integrated with the project
        if self._is_feature_already_integrated(feature, project):
            raise ValidationError(
                f"Feature '{feature.uuid}' is already integrated with project '{project.uuid}'."
            )

        # Create IntegratedFeature
        integrated_feature = self._create_integrated_feature(
            feature, project, user, request_data.get("created_by_vtex", False)
        )

        # Execute install actions based on feature config
        self.install_actions.execute(
            integrated_feature=integrated_feature,
            feature=feature,
            project_uuid=request_data["project_uuid"],
            store=request_data["store"],
            flows_channel_uuid=request_data["flows_channel_uuid"],
            wpp_cloud_app_uuid=request_data["wpp_cloud_app_uuid"]
        )

        # Process sectors and globals
        self._process_sectors(
            integrated_feature, feature, request_data.get("sectors", [])
        )
        self._process_globals(
            integrated_feature, feature, request_data.get("globals_values", {})
        )

        # Publish integration event
        self._publish_integration_event(integrated_feature)

        # Prepare and return the response data
        response_data = self._prepare_response_data(integrated_feature)

        return response_data

    def _get_feature(self, feature_uuid):
        try:
            return Feature.objects.get(uuid=feature_uuid)
        except Feature.DoesNotExist:
            raise NotFound(f"Feature with uuid '{feature_uuid}' does not exist.")

    def _get_project(self, project_uuid):
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise NotFound(f"Project with uuid '{project_uuid}' does not exist.")

    def _is_feature_already_integrated(self, feature, project):
        """
        Check if the feature is already integrated with the given project.

        Args:
            feature (Feature): The feature to check.
            project (Project): The project to check.

        Returns:
            bool: True if the feature is already integrated with the project, False otherwise.
        """
        return IntegratedFeature.objects.filter(
            feature=feature, project=project
        ).exists()

    def _create_integrated_feature(self, feature, project, user, created_by_vtex):
        feature_version = feature.last_version
        integrated_feature = IntegratedFeature.objects.create(
            project=project,
            feature=feature,
            feature_version=feature_version,
            user=user,
            created_by_vtex=created_by_vtex,
        )
        return integrated_feature

    def _process_sectors(self, integrated_feature, feature, sectors_request):
        """
        Process and set the sectors for the integrated feature.

        Args:
            integrated_feature (IntegratedFeature): The integrated feature instance.
            feature (Feature): The feature being integrated.
            sectors_request (list): List of sectors provided in the request.
        """
        integrated_feature.sectors = []
        if feature.last_version.sectors:
            for sector in feature.last_version.sectors:
                matching_sector = next(
                    (s for s in sectors_request if s.get("name") == sector.get("name")),
                    None,
                )
                if matching_sector:
                    new_sector = {
                        "name": matching_sector.get("name"),
                        "tags": matching_sector.get("tags"),
                        "queues": sector.get("queues"),
                    }
                    integrated_feature.sectors.append(new_sector)
        integrated_feature.save()

    def _process_globals(self, integrated_feature, feature, globals_values_request):
        """
        Process and populate the global variables for the integrated feature.

        Args:
            integrated_feature (IntegratedFeature): The integrated feature instance.
            feature (Feature): The feature being integrated.
            globals_values_request (dict): Global values provided in the request.
        """
        # Initialize full_globals_values with all globals from feature_version, setting them to empty strings
        feature_version = feature.last_version
        full_globals_values = {
            global_var: "" for global_var in feature_version.globals_values
        }

        # Update with any provided values from the request
        full_globals_values.update(globals_values_request)

        # Treat and fill specific globals
        fill_globals_usecase = PopulateGlobalsValuesUsecase(
            self.integrations_service, self.flows_service
        )
        treated_globals_values = fill_globals_usecase.execute(
            full_globals_values,
            integrated_feature.user.email,
            str(integrated_feature.project.uuid),
        )

        # If created by VTEX, populate default globals from config
        if integrated_feature.created_by_vtex:
            populate_defaults_use_case = PopulateDefaultsUseCase()
            default_globals_values = populate_defaults_use_case.execute(
                feature, full_globals_values
            )
            # Merge default globals into treated_globals_values
            treated_globals_values.update(default_globals_values)

        # Ensure all globals are included
        integrated_feature.globals_values = treated_globals_values
        integrated_feature.save()

    def _publish_integration_event(self, integrated_feature):
        """
        Publish the integration event to the message broker.

        Args:
            integrated_feature (IntegratedFeature): The integrated feature instance.
        """
        # Prepare data for publishing
        sectors_data = [
            {
                "name": sector.get("name", ""),
                "tags": sector.get("tags", ""),
                "service_limit": 4,
                "working_hours": {"init": "08:00", "close": "18:00"},
                "queues": sector.get("queues", []),
            }
            for sector in integrated_feature.sectors
        ]

        actions = []
        feature_version = integrated_feature.feature_version
        for function in integrated_feature.feature.functions.all():
            function_last_version = function.last_version
            if function_last_version.action_base_flow_uuid:
                actions.append(
                    {
                        "name": function_last_version.action_name,
                        "prompt": function_last_version.action_prompt,
                        "root_flow_uuid": str(
                            function_last_version.action_base_flow_uuid
                        ),
                        "type": "",
                    }
                )

        if feature_version.action_base_flow_uuid:
            actions.append(
                {
                    "name": feature_version.action_name,
                    "prompt": feature_version.action_prompt,
                    "root_flow_uuid": str(feature_version.action_base_flow_uuid),
                    "type": "",
                }
            )

        body = {
            "definition": feature_version.definition,
            "user_email": integrated_feature.user.email,
            "project_uuid": str(integrated_feature.project.uuid),
            "parameters": integrated_feature.globals_values,
            "feature_version": str(feature_version.uuid),
            "feature_uuid": str(feature_version.feature.uuid),
            "sectors": sectors_data,
            "action": actions,
        }

        IntegratedFeatureEDA().publisher(body=body, exchange="integrated-feature.topic")
        print(f"message sent `integrated feature` - body: {body}")

    def _prepare_response_data(self, integrated_feature):
        """
        Prepare the response data to be sent back to the client.

        Args:
            integrated_feature (IntegratedFeature): The integrated feature instance.

        Returns:
            dict: Response data including additional info if necessary.
        """
        serializer = IntegratedFeatureSerializer(integrated_feature.feature)
        response_data = {
            "status": 200,
            "data": {
                "feature": str(integrated_feature.feature.uuid),
                "integrated_feature": str(integrated_feature.uuid),
                "feature_version": str(integrated_feature.feature_version.uuid),
                "project": str(integrated_feature.project.uuid),
                "user": integrated_feature.user.email,
                "integrated_on": integrated_feature.integrated_on.isoformat(),
                **serializer.data,
            },
        }

        return response_data
