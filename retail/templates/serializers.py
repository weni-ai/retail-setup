from rest_framework import serializers

from retail.templates.models import Template


class CreateTemplateSerializer(serializers.Serializer):
    template_translation = serializers.JSONField(required=True)
    template_name = serializers.CharField(required=True)
    category = serializers.CharField(required=True)
    start_condition = serializers.CharField(required=True)
    app_uuid = serializers.CharField(required=True)
    project_uuid = serializers.CharField(required=True)
    rule_code = serializers.CharField(required=False)


class ReadTemplateSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    start_condition = serializers.CharField()
    status = serializers.SerializerMethodField()
    rule_code = serializers.CharField()

    def get_status(self, obj: Template) -> str:
        if obj.current_version is not None:
            return obj.current_version.status

        return "PENDING"


class UpdateTemplateSerializer(serializers.Serializer):
    status = serializers.CharField(required=True)
    version_uuid = serializers.UUIDField(required=True)


class CreateLibraryTemplateSerializer(serializers.Serializer):
    library_template_name = serializers.CharField(required=True)
    category = serializers.CharField(required=True)
    language = serializers.CharField(required=True)
    app_uuid = serializers.CharField(required=True)
    project_uuid = serializers.CharField(required=True)
    start_condition = serializers.CharField(required=True)
    library_template_button_inputs = serializers.ListField(required=False)


class UpdateTemplateBodySerializer(serializers.Serializer):
    template_body = serializers.CharField(required=True)
    app_uuid = serializers.CharField(required=True)
    project_uuid = serializers.CharField(required=True)
