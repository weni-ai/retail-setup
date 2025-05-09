from rest_framework import serializers

from retail.templates.models import Template


class CreateTemplateSerializer(serializers.Serializer):
    template_translation = serializers.JSONField(required=True)
    template_name = serializers.CharField(required=True)
    category = serializers.CharField(required=True)
    start_condition = serializers.CharField(required=True)
    app_uuid = serializers.CharField(required=True)
    project_uuid = serializers.CharField(required=True)


class ReadTemplateSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    start_condition = serializers.CharField()
    status = serializers.SerializerMethodField()

    def get_status(self, obj: Template) -> str:
        if obj.current_version is not None:
            return obj.current_version.status

        return "PENDING"
