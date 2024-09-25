from django.contrib.auth.models import User

from rest_framework import views, viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


from retail.api.integrated_feature.serializers import IntegratedFeatureSerializer
from retail.features.models import Feature, IntegratedFeature
from retail.features.integrated_feature_eda import IntegratedFeatureEDA
from retail.projects.models import Project


class IntegratedFeatureView(views.APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        print(request.data, request.query_params, args, kwargs)
        feature = Feature.objects.get(uuid=kwargs["feature_uuid"])
        try:
            project = Project.objects.get(uuid=request.data["project_uuid"])
        except Project.DoesNotExist:
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={
                    "error": f"Project with uuid equals {request.data['project_uuid' ]} does not exists!"
                },
            )
        print(request._user.__dict__)
        user, _ = User.objects.get_or_create(email=request.user.email)
        last_version = feature.last_version

        integrated_feature = IntegratedFeature.objects.create(
            project=project, feature=feature, feature_version=last_version, user=user
        )

        body = {
            "definition": integrated_feature.feature_version.definition,
            "user_email": integrated_feature.user.email,
            "project_uuid": str(integrated_feature.project.uuid),
            "parameters": integrated_feature.globals_values,
            "feature_version": str(integrated_feature.feature_version.uuid),
            "feature_uuid": str(integrated_feature.feature.uuid),
            # "sectors": sectors_data,
            "action": {
                "name": integrated_feature.feature_version.action_name,
                "prompt": integrated_feature.feature_version.action_prompt,
                "root_flow_uuid": integrated_feature.action_base_flow,
            },
        }

        IntegratedFeatureEDA().publisher(body=body, exchange="integrated-feature.topic")
        print(f"message send `integrated feature` - body: {body}")

        response = {}
        return Response(response)

    def get(self, request, project_uuid):
        try:

            category = request.query_params.get("category", None)
            integrated_features = IntegratedFeature.objects.filter(
                project__uuid=project_uuid
            ).values_list("feature__uuid", flat=True)

            features = Feature.objects.filter(uuid__in=integrated_features)

            if category:
                features = features.filter(category=category)

            serializer = IntegratedFeatureSerializer(features, many=True)

            return Response({"results": serializer.data}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
