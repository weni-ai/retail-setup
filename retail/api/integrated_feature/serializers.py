from rest_framework import serializers

from retail.features.models import Feature


class IntegratedFeatureSerializer(serializers.Serializer):
    feature_uuid = serializers.SerializerMethodField()
    name = serializers.CharField()
    description = serializers.CharField()
    disclaimer = serializers.CharField()
    documentation_url = serializers.CharField()
    globals = serializers.SerializerMethodField()
    sectors = serializers.SerializerMethodField()

    def get_feature_uuid(self, obj):
        return obj.uuid

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
        )


class IntegratedFeatureSettingsSerializer(serializers.Serializer):
    project_uuid = serializers.UUIDField(required=True)
    integration_settings = serializers.JSONField(required=True)
