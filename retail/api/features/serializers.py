from rest_framework import serializers

from retail.features.models import Feature


class FeaturesSerializer(serializers.Serializer):
    feature_uuid = serializers.SerializerMethodField()
    name = serializers.CharField()
    description = serializers.CharField()
    disclaimer = serializers.CharField()
    documentation_url = serializers.CharField()
    globals = serializers.SerializerMethodField()
    sectors = serializers.SerializerMethodField()
    initial_flow = serializers.SerializerMethodField()

    def get_feature_uuid(self, obj):
        return obj.uuid

    def get_globals(self, obj):
        last_version = obj.last_version
        globals_values = last_version.globals_values if last_version else []
        for function in obj.functions.all():
            function_last_version = function.last_version
            for function_global in function_last_version.globals_values:
                if function_global not in globals_values:
                    globals_values.append(function_global)
        return globals_values

    def get_sectors(self, obj):
        last_version = obj.last_version
        sectors = []
        if last_version and last_version.sectors:
            sectors = [
                sector.get("name")
                for sector in last_version.sectors
                if sector.get("name")
            ]
        for function in obj.functions.all():
            function_last_version = function.last_version
            for sector in function_last_version.sectors:
                if sector.get("name") not in sectors:
                    sectors.append(sector.get("name"))
        return sectors

    def get_initial_flow(self, obj):
        last_version = obj.last_version
        if last_version:
            flows = last_version.get_flows_base()
            return [
                {"uuid": flow["flow_uuid"], "name": flow["flow_name"]} for flow in flows
            ]
        return []

    class Meta:
        model = Feature
        fields = (
            "uuid",
            "name",
            "description",
            "disclaimer",
            "documentation_url",
            "globals",
            "sectors",
            "initial_flow",
        )
