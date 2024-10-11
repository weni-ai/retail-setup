from rest_framework import serializers

from retail.features.models import Feature


class ListIntegratedFeatureSerializer(serializers.Serializer):
    name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    disclaimer = serializers.SerializerMethodField()
    documentation_url = serializers.SerializerMethodField()
    feature_uuid = serializers.SerializerMethodField()
    globals = serializers.SerializerMethodField()
    sectors = serializers.SerializerMethodField()
    version = serializers.SerializerMethodField()
    versions = serializers.SerializerMethodField()

    def get_name(self, obj):
        return obj.feature.name
    
    def get_description(self, obj):
        return obj.feature.description
    
    def get_disclaimer(self, obj):
        return obj.feature.disclaimer
    
    def get_documentation_url(self, obj):
        return obj.feature.documentation_url
    
    def get_feature_uuid(self, obj):
        return obj.feature.uuid
    
    def get_version(self, obj):
        return obj.feature_version.version

    def get_versions(self, obj):
        versions = []
        for version in obj.feature.versions.all():
            body = {
                "version": version.version,
                "globals": version.globals_values,
                "sectors": []
            }
            for sector in version.sectors:
                body["sectors"].append({"name": sector.get("name", ""), "tags": sector.get("tags")})
            versions.append(body)

        return versions


    def get_globals(self, obj):
        return obj.globals_values
    
    def get_sectors(self, obj):
        sectors_list = []
        for sector in obj.sectors:
            sectors_list.append({"name": sector.get("name"), "tags": sector.get("tags", [])})
        return sectors_list


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
