from django.conf import settings

from rest_framework import status
from rest_framework.response import Response

from retail.api.base_service_view import BaseServiceView
from retail.api.features.serializers import (
    FeatureQueryParamsSerializer,
    FeaturesSerializer,
)

from retail.api.usecases.remove_globals_keys import RemoveGlobalsKeysUsecase
from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project


class FeaturesView(BaseServiceView):
    def get(self, request, project_uuid: str):
        try:
            serializer = FeatureQueryParamsSerializer(data=request.query_params)
            serializer.is_valid(raise_exception=True)
            params = serializer.validated_data

            category = params.get("category")
            can_vtex_integrate = params.get("can_vtex_integrate")
            nexus_agents = params.get("nexus_agents")

            integrated_features = IntegratedFeature.objects.filter(
                project__uuid=project_uuid
            ).values_list("feature__uuid", flat=True)

            features = Feature.objects.exclude(uuid__in=integrated_features)
            features = features.exclude(feature_type="FUNCTION")
            features = features.exclude(status="development")

            can_testing = any(
                email in request.user.email for email in settings.EMAILS_CAN_TESTING
            )

            if not can_testing:
                features = features.exclude(status="testing")

            if category:
                features = features.filter(category=category)

            if can_vtex_integrate is not None:
                features = features.filter(can_vtex_integrate=can_vtex_integrate)

            serializer = FeaturesSerializer(features, many=True)

            usecase = RemoveGlobalsKeysUsecase(
                integrations_service=self.integrations_service,
                flows_service=self.flows_service,
            )

            # Execute usecase to modify globals
            user_email = request.user.email
            features_data = usecase.execute(serializer.data, user_email, project_uuid)
            project = Project.objects.get(uuid=project_uuid)
            vtex_config = project.config.get("vtex_config", {})

            response_data = {
                "results": features_data,
                "store_type": vtex_config.get("vtex_store_type", ""),
            }

            # If nexus_agents parameter is provided, fetch and include agent data from Nexus service
            if nexus_agents:
                agents_data = self.nexus_service.list_agents(project_uuid)
                if agents_data:
                    response_data["nexus_agents"] = agents_data

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
