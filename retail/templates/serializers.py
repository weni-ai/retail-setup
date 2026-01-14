from rest_framework import serializers

from retail.templates.models import Template
from retail.services.aws_s3.service import S3Service


class TemplateHeaderSerializer(serializers.Serializer):
    """Serializer for template header with presigned URL generation."""

    header_type = serializers.CharField()
    text = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        self.s3_service = kwargs.pop("s3_service", None)
        super().__init__(*args, **kwargs)

    def get_text(self, header_data):
        """
        Returns presigned URL for IMAGE headers or plain text for TEXT headers.
        """
        text = header_data.get("text", "")
        header_type = header_data.get("header_type", "TEXT")

        if header_type == "IMAGE" and text and self.s3_service:
            if not text.startswith(("http://", "https://", "s3://")):
                try:
                    return self.s3_service.generate_presigned_url(text)
                except Exception:
                    return text

        return text


class TemplateMetadataSerializer(serializers.Serializer):
    """Serializer for template metadata with proper header handling."""

    body = serializers.CharField(allow_null=True, required=False)
    body_params = serializers.JSONField(allow_null=True, required=False)
    header = serializers.SerializerMethodField()
    footer = serializers.CharField(allow_null=True, required=False)
    buttons = serializers.JSONField(allow_null=True, required=False)
    category = serializers.CharField(allow_null=True, required=False)

    def __init__(self, *args, **kwargs):
        self.s3_service = kwargs.pop("s3_service", None)
        super().__init__(*args, **kwargs)

    def get_header(self, metadata):
        """
        Serializes header with presigned URL if it's an image.
        """
        header = metadata.get("header")
        if not header:
            return None

        header_serializer = TemplateHeaderSerializer(header, s3_service=self.s3_service)
        return header_serializer.data


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
    metadata = serializers.SerializerMethodField()
    is_custom = serializers.BooleanField()
    needs_button_edit = serializers.BooleanField()
    deleted_at = serializers.DateTimeField()
    is_active = serializers.BooleanField()
    variables = serializers.JSONField()

    def __init__(self, *args, **kwargs):
        self.s3_service = kwargs.pop("s3_service", None)

        if self.s3_service is None:
            try:
                self.s3_service = S3Service()
            except Exception:
                self.s3_service = None
        super().__init__(*args, **kwargs)

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

    def get_metadata(self, obj: Template):
        """
        Serializes metadata with presigned URLs for images.
        """
        if not obj.metadata:
            return {}

        metadata_serializer = TemplateMetadataSerializer(
            obj.metadata, s3_service=self.s3_service
        )
        return metadata_serializer.data


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


class ParameterSerializer(serializers.Serializer):
    name = serializers.CharField()
    value = serializers.JSONField()


class UpdateTemplateContentSerializer(serializers.Serializer):
    template_body = serializers.CharField(required=False)
    template_header = serializers.CharField(required=False)
    template_footer = serializers.CharField(required=False)
    template_button = serializers.ListField(required=False)
    template_body_params = serializers.ListField(required=False)
    app_uuid = serializers.CharField(required=True)
    project_uuid = serializers.CharField(required=True)
    parameters = ParameterSerializer(many=True, required=False, allow_null=True)
    language = serializers.CharField(required=False, allow_null=True)

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
    language = serializers.CharField(required=False, allow_null=True)


class CreateCustomTemplateSerializer(serializers.Serializer):
    template_translation = serializers.JSONField(required=True)
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
