from django.contrib.auth.models import User

from rest_framework import status
from rest_framework.response import Response

from retail.api.base_service_view import BaseServiceView
from retail.api.integrated_feature.serializers import IntegratedFeatureSerializer
from retail.api.usecases.populate_globals_values import PopulateGlobalsValuesUsecase

from retail.features.models import Feature, IntegratedFeature
from retail.features.integrated_feature_eda import IntegratedFeatureEDA
from retail.projects.models import Project


class IntegratedFeatureView(BaseServiceView):
    def post(self, request, *args, **kwargs):
        feature = Feature.objects.get(uuid=kwargs["feature_uuid"])
        try:
            project = Project.objects.get(uuid=request.data["project_uuid"])
        except Project.DoesNotExist:
            return Response(
                status=status.HTTP_404_NOT_FOUND,
                data={
                    "error": f"Project with uuid equals {request.data['project_uuid']} does not exist!"
                },
            )

        user, _ = User.objects.get_or_create(email=request.user.email)
        feature_version = feature.last_version

        integrated_feature = IntegratedFeature.objects.create(
            project=project, feature=feature, feature_version=feature_version, user=user
        )

        sectors_data = []
        integrated_feature.sectors = []
        if feature_version.sectors is not None:
            for sector in feature_version.sectors:
                for r_sector in request.data.get("sectors", []):
                    if r_sector.get("name") == sector.get("name"):
                        new_sector = {
                            "name": r_sector.get("name"),
                            "tags": r_sector.get("tags"),
                            "queues": sector.get("queues"),
                        }
                        integrated_feature.sectors.append(new_sector)
                        break

        # Treat and fill specific globals
        fill_globals_usecase = PopulateGlobalsValuesUsecase(
            self.integrations_service, self.flows_service
        )
        globals_values_request = {}
        for globals_values in feature_version.globals_values:
            globals_values_request[globals_values] = ""

        for key, value in request.data.get("globals_values", {}).items():
            globals_values_request[key] = value

        treated_globals_values = fill_globals_usecase.execute(
            globals_values_request,
            request.user.email,
            request.data["project_uuid"],
        )

        # Add all globals from the request, including treated ones
        for globals_key, globals_value in treated_globals_values.items():
            integrated_feature.globals_values[globals_key] = globals_value

        for sector in integrated_feature.sectors:
            sectors_data.append(
                {
                    "name": sector.get("name", ""),
                    "tags": sector.get("tags", ""),
                    "service_limit": 4,
                    "working_hours": {"init": "08:00", "close": "18:00"},
                    "queues": sector.get("queues", []),
                }
            )

        actions = []
        for function in feature.functions.all():
            function_last_version = function.last_version
            if function_last_version.action_base_flow_uuid is not None:
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
            "definition": integrated_feature.feature_version.definition,
            "user_email": integrated_feature.user.email,
            "project_uuid": str(integrated_feature.project.uuid),
            "parameters": integrated_feature.globals_values,
            "feature_version": str(integrated_feature.feature_version.uuid),
            "feature_uuid": str(integrated_feature.feature.uuid),
            "sectors": sectors_data,
            "action": actions,
        }

        IntegratedFeatureEDA().publisher(body=body, exchange="integrated-feature.topic")
        print(f"message sent `integrated feature` - body: {body}")

        serializer = IntegratedFeatureSerializer(integrated_feature.feature)

        response = {
            "status": 200,
            "data": {
                "feature": integrated_feature.feature.uuid,
                "feature_version": integrated_feature.feature_version.uuid,
                "project": integrated_feature.project.uuid,
                "user": integrated_feature.user.email,
                "integrated_on": integrated_feature.integrated_on,
                **serializer.data,
            },
        }
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
            "feature_version": str(integrated_feature.feature_version.uuid),
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
        integrated_feature.save()
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
                },
            }
        )
