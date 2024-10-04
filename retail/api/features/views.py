from rest_framework import views, status
from rest_framework.response import Response

from retail.api.base_service_view import BaseServiceView
from retail.api.features.serializers import FeaturesSerializer
from retail.api.usecases.remove_globals_keys import RemoveGlobalsKeysUsecase
from retail.features.models import Feature, IntegratedFeature


class FeaturesView(BaseServiceView):
    def get(self, request, project_uuid: str):
        try:
            category = request.query_params.get("category", None)

            integrated_features = IntegratedFeature.objects.filter(
                project__uuid=project_uuid
            ).values_list("feature__uuid", flat=True)

            features = Feature.objects.exclude(uuid__in=integrated_features)
            features = features.exclude(feature_type="FUNCTION")
            features = features.exclude(status="development")
            features = features.exclude(status="testing")
            if category:
                features = features.filter(category=category)

            serializer = FeaturesSerializer(features, many=True)

            usecase = RemoveGlobalsKeysUsecase(
                integrations_service=self.integrations_service,
                flows_service=self.flows_service,
            )

            # Execute usecase to modify globals
            user_email = request.user.email
            features_data = usecase.execute(serializer.data, user_email, project_uuid)

            return Response({"results": features_data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
