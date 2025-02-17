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
    category = serializers.CharField()
    code = serializers.SerializerMethodField()
    config = serializers.SerializerMethodField()

    def get_feature_uuid(self, obj):
        return obj.uuid

    def get_globals(self, obj):
        last_version = obj.last_version

        if not last_version:
            return []

        if not last_version.globals_values:
            return []

        return last_version.globals_values

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

    def get_code(self, obj):
        return obj.code

    def get_config(self, obj):
        return obj.config

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
            "category",
            "code",
        )
