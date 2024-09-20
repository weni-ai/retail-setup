from rest_framework import serializers

from retail.features.models import Feature


class IntegratedFeatureSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    disclaimer = serializers.CharField()
    documentation_url = serializers.CharField()
    globals = serializers.SerializerMethodField()
    sectors = serializers.SerializerMethodField()
    initial_flow = serializers.SerializerMethodField()

    def get_globals(self, obj):
        integrated_features = obj.integrated_features.all()

        globals_list = []
        for integrated_feature in integrated_features:
            if isinstance(integrated_feature.globals_values, dict):
                globals_list.extend(
                    [
                        {"name": key, "value": value}
                        for key, value in integrated_feature.globals_values.items()
                    ]
                )

        return globals_list

    def get_sectors(self, obj):
        integrated_features = obj.integrated_features.all()

        sectors_list = []
        for integrated_feature in integrated_features:
            if isinstance(integrated_feature.sectors, list):
                for sector in integrated_feature.sectors:
                    if (
                        isinstance(sector, dict)
                        and "name" in sector
                        and "tags" in sector
                    ):
                        sectors_list.append(
                            {"name": sector.get("name"), "tags": sector.get("tags", [])}
                        )

        return sectors_list

    def get_initial_flow(self, obj):
        last_version = obj.last_version
        if not last_version:
            return []

        flows = last_version.get_flows_base()
        integrated_features = obj.integrated_features.all()
        initial_flows = []

        for flow in flows:
            is_base_flow = False

            for integrated_feature in integrated_features:
                if integrated_feature.action_base_flow == flow["flow_uuid"]:
                    is_base_flow = True
                    break

            initial_flows.append(
                {
                    "uuid": flow["flow_uuid"],
                    "name": flow["flow_name"],
                    "is_base_flow": is_base_flow,
                }
            )

        return initial_flows

    class Meta:
        model = Feature
        fields = (
            "name",
            "description",
            "disclaimer",
            "documentation_url",
            "globals",
            "sectors",
            "initial_flow",
        )
