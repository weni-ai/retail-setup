from rest_framework import serializers

from retail.templates.models import Template


class CreateTemplateSerializer(serializers.Serializer):
    template_translation = serializers.JSONField(required=True)
    template_name = serializers.CharField(required=True)
    category = serializers.CharField(required=True)
    app_uuid = serializers.CharField(required=True)
    project_uuid = serializers.CharField(required=True)
    rule_code = serializers.CharField(required=False)


class ReadTemplateSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    display_name = serializers.SerializerMethodField()
    start_condition = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    rule_code = serializers.CharField()
    metadata = serializers.JSONField()
    is_custom = serializers.BooleanField()
    needs_button_edit = serializers.BooleanField()

    def get_status(self, obj: Template) -> str:
        last_version = obj.versions.order_by("-id").first()

        if last_version is None:
            return "PENDING"

        return last_version.status

    def get_display_name(self, obj: Template) -> str:
        if obj.parent is None:
            return obj.display_name

        return obj.parent.display_name

    def get_start_condition(self, obj: Template) -> str:
        if obj.parent is None:
            return obj.start_condition

        return obj.parent.start_condition


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


class UpdateTemplateContentSerializer(serializers.Serializer):
    template_body = serializers.CharField(required=False)
    template_header = serializers.CharField(required=False)
    template_footer = serializers.CharField(required=False)
    template_button = serializers.ListField(required=False)
    app_uuid = serializers.CharField(required=True)
    project_uuid = serializers.CharField(required=True)

    def validate(self, attrs):
        if not any(
            attrs.get(field)
            for field in ("template_body", "template_header", "template_footer")
        ):
            raise serializers.ValidationError(
                "At least one of 'template_body', 'template_header', or 'template_footer' must be provided."
            )
        return attrs


class UpdateLibraryTemplateButtonUrlSerializer(serializers.Serializer):
    base_url = serializers.CharField()
    url_suffix_example = serializers.CharField(required=False)


class UpdateLibraryTemplateButtonSerializer(serializers.Serializer):
    type = serializers.CharField()
    url = UpdateLibraryTemplateButtonUrlSerializer()


class UpdateLibraryTemplateSerializer(serializers.Serializer):
    library_template_button_inputs = UpdateLibraryTemplateButtonSerializer(many=True)


class ParameterSerializer(serializers.Serializer):
    name = serializers.CharField()
    value = serializers.JSONField()


class CreateCustomTemplateSerializer(serializers.Serializer):
    template_translation = serializers.JSONField(required=True)
    template_name = serializers.CharField()
    category = serializers.CharField()
    app_uuid = serializers.CharField(required=True)
    project_uuid = serializers.CharField(required=True)
    integrated_agent_uuid = serializers.CharField(required=True)
    parameters = ParameterSerializer(many=True, required=True)
    display_name = serializers.CharField(required=True)


class TemplateMetricsRequestSerializer(serializers.Serializer):
    template_uuid = serializers.UUIDField(required=True)
    start = serializers.CharField(required=True)
    end = serializers.CharField(required=True)
