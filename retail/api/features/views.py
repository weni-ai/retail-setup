from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


from retail.api.features.serializers import FeaturesSerializer
from retail.api.usecases.build_external_globals import BuildExternalGlobalsUsecase
from retail.clients.flows.client import FlowsClient
from retail.clients.integrations.client import IntegrationsClient
from retail.features.models import Feature, IntegratedFeature
from retail.services.flows.service import FlowsService
from retail.services.integrations.service import IntegrationsService


class FeaturesView(views.APIView):
    permission_classes = [IsAuthenticated]

    integrations_service_class = IntegrationsService
    flows_service_class = FlowsService
    integrations_client_class = IntegrationsClient
    flows_client_class = FlowsClient

    _integrations_service = None
    _flows_service = None

    @property
    def integrations_service(self):
        if not self._integrations_service:
            self._integrations_service = self.integrations_service_class(
                self.integrations_client_class()
            )
        return self._integrations_service

    @property
    def flows_service(self):
        if not self._flows_service:
            self._flows_service = self.flows_service_class(self.flows_client_class())
        return self._flows_service

    def get(self, request, project_uuid: str):
        try:
            category = request.query_params.get("category", None)

            integrated_features = IntegratedFeature.objects.filter(
                project__uuid=project_uuid
            ).values_list("feature__uuid", flat=True)

            features = Feature.objects.exclude(uuid__in=integrated_features)
            features = features.exclude(feature_type="FUNCTION")
            if category:
                features = features.filter(category=category)

            serializer = FeaturesSerializer(features, many=True)

            usecase = BuildExternalGlobalsUsecase(
                integrations_service=self.integrations_service,
                flows_service=self.flows_service,
            )

            # execute usecase to modify globals
            user_email = request.user.email
            features_data = usecase.execute(serializer.data, user_email, project_uuid)

            return Response({"results": features_data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
