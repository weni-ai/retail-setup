from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


from retail.api.features.serializers import FeaturesSerializer
from retail.features.models import Feature, IntegratedFeature


class FeaturesView(views.APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        try:

            category = request.query_params.get("category", None)
            integrated_features = IntegratedFeature.objects.filter(
                project__uuid=project_uuid
            ).values_list("feature__uuid", flat=True)

            features = Feature.objects.exclude(uuid__in=integrated_features)

            if category:
                features = features.filter(category=category)

            serializer = FeaturesSerializer(features, many=True)

            return Response({"results": serializer.data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
