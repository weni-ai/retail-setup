from rest_framework import serializers

from retail.features.models import Feature


class FeaturesSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    disclaimer = serializers.CharField()
    documentation_url = serializers.CharField()
    globals = serializers.SerializerMethodField()
    sectors = serializers.SerializerMethodField()
    initial_flow = serializers.SerializerMethodField()

    def get_globals(self, obj):
        last_version = obj.last_version
        return last_version.globals_values if last_version else None

    def get_sectors(self, obj):
        last_version = obj.last_version
        if last_version and last_version.sectors:
            return [
                sector.get("name")
                for sector in last_version.sectors
                if sector.get("name")
            ]
        return []

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
            "name",
            "description",
            "disclaimer",
            "documentation_url",
            "globals",
            "sectors",
            "initial_flow",
        )
