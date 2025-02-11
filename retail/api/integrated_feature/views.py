from django.contrib.auth.models import User

from django.shortcuts import get_object_or_404
from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from retail.api.base_service_view import BaseServiceView
from retail.api.integrated_feature.serializers import (
    IntegratedFeatureSettingsSerializer,
    IntegratedFeatureSerializer,
    AppIntegratedFeatureSerializer,
)
from retail.api.usecases.create_integrated_feature_usecase import (
    CreateIntegratedFeatureUseCase,
)
from retail.api.usecases.populate_globals_values import PopulateGlobalsValuesUsecase

from retail.api.usecases.populate_globals_with_defaults import PopulateDefaultsUseCase
from retail.features.models import Feature, IntegratedFeature
from retail.features.integrated_feature_eda import IntegratedFeatureEDA
from retail.projects.models import Project


class IntegratedFeatureView(BaseServiceView):
    def post(self, request, *args, **kwargs):
        user, _ = User.objects.get_or_create(
            email=request.user.email, defaults={"username": request.user.email}
        )
        request_data = request.data.copy()
        request_data["feature_uuid"] = kwargs.get("feature_uuid")

        use_case = CreateIntegratedFeatureUseCase(
            integrations_service=self.integrations_service,
            flows_service=self.flows_service,
        )

        response_data = use_case.execute(request_data, user)
        return Response(response_data, status=status.HTTP_200_OK)

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

    def delete(self, request, *args, **kwargs):
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

        integrated_feature = IntegratedFeature.objects.get(
            project__uuid=str(project.uuid), feature__uuid=str(feature.uuid)
        )

        body = {
            "project_uuid": str(project.uuid),
            "feature_version": (
                str(integrated_feature.feature_version.uuid)
                if integrated_feature.feature_version
                else ""
            ),
            "feature_uuid": str(integrated_feature.feature.uuid),
            "user_email": request.user.email,
        }

        IntegratedFeatureEDA().publisher(body=body, exchange="removed-feature.topic")
        print(f"message send to `removed-feature.topic`: {body}")
        integrated_feature.delete()
        return Response({"status": 200, "data": "integrated feature removed"})

    def put(self, request, *args, **kwargs):
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
        integrated_feature = IntegratedFeature.objects.get(
            project=project, feature=feature
        )
        for key, value in request.data.get("globals_values").items():
            integrated_feature.globals_values[key] = value

        for sector in request.data.get("sectors", []):
            for integrated_sector in integrated_feature.sectors:
                if integrated_sector["name"] == sector["name"]:
                    integrated_sector["tags"] = sector["tags"]
        integrated_feature.save()

        return Response(
            {
                "status": 200,
                "data": {
                    "message": "Integrated feature updated",
                    "globals_values": integrated_feature.globals_values,
                    "sectors": integrated_feature.sectors,
                    "config": integrated_feature.config,
                },
            }
        )


class IntegratedFeatureSettingsView(views.APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        serializer = IntegratedFeatureSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        feature_uuid = kwargs["feature_uuid"]
        project_uuid = request.data["project_uuid"]
        integration_settings = request.data["integration_settings"]

        integrated_feature: IntegratedFeature = get_object_or_404(
            IntegratedFeature, feature__uuid=feature_uuid, project__uuid=project_uuid
        )

        config = integrated_feature.config
        config["integration_settings"] = integration_settings

        integrated_feature.config = config
        integrated_feature.save()

        return Response(config, status=status.HTTP_200_OK)

class AppIntegratedFeatureView(BaseServiceView):
    def get(self, request, project_uuid, *args, **kwargs):
        try:
            category = request.query_params.get("category", None)
            integrated_features = IntegratedFeature.objects.filter(
                project__uuid=project_uuid
            ).values_list("feature__uuid", flat=True)

            if category:
                integrated_features = integrated_features.filter(category=category)

            serializer = AppIntegratedFeatureSerializer(integrated_features, many=True)

            return Response({"results": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

