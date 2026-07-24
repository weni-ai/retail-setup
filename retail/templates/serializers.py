from rest_framework import serializers

from retail.templates.adapters.template_library_to_custom_adapter import (
    HeaderTransformer,
)
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
    language = serializers.CharField(allow_null=True, required=False)

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
    app_uuid = serializers.SerializerMethodField()

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

    def get_app_uuid(self, obj: Template) -> str | None:
        first_version = obj.versions.order_by("id").first()
        if not first_version or not first_version.integrations_app_uuid:
            return None

        return str(first_version.integrations_app_uuid)


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


def _normalize_blank_footer(value: str | None) -> str | None:
    """Blank or whitespace-only footer means explicit removal."""
    if value is None:
        return None
    if value.strip() == "":
        return None
    return value


class UpdateTemplateContentSerializer(serializers.Serializer):
    template_body = serializers.CharField(required=False)
    template_header = serializers.CharField(required=False)
    template_footer = serializers.CharField(required=False, allow_blank=True)
    template_button = serializers.ListField(required=False)
    template_body_params = serializers.ListField(required=False)
    app_uuid = serializers.CharField(required=True)
    project_uuid = serializers.CharField(required=True)
    parameters = ParameterSerializer(many=True, required=False, allow_null=True)
    language = serializers.CharField(required=False, allow_null=True)

    def validate_template_footer(self, value: str | None) -> str | None:
        return _normalize_blank_footer(value)

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


class ValidateTemplateSampleSerializer(UpdateTemplateContentSerializer):
    """Serializer for ``POST /api/v3/templates/<uuid>/sample/``.

    Schema-compatible with ``UpdateTemplateContentSerializer``; layers
    on length caps and button-mode disjointness. The tenant-authority
    check (body ``project_uuid`` vs. the authenticated project) lives in
    the view, which owns the auth context. Anchor: FR-003 / FR-003a /
    FR-014 (see ``specs/004-template-sample-validation/spec.md``).
    """

    _BODY_MAX_LENGTH = 1024
    _HEADER_TEXT_MAX_LENGTH = 60
    _FOOTER_MAX_LENGTH = 60
    _BUTTON_TEXT_MAX_LENGTH = 20
    _MAX_URL_BUTTONS = 1
    _MAX_QUICK_REPLY_BUTTONS = 3

    _URL_BUTTON_TYPE = "URL"
    _QUICK_REPLY_BUTTON_TYPE = "QUICK_REPLY"

    def validate_template_body(self, value: str) -> str:
        if value and len(value) > self._BODY_MAX_LENGTH:
            raise serializers.ValidationError(
                f"Ensure this field has no more than {self._BODY_MAX_LENGTH} characters."
            )
        return value

    def validate_template_header(self, value: str) -> str:
        if value and self._is_plain_text_header(value):
            if len(value) > self._HEADER_TEXT_MAX_LENGTH:
                raise serializers.ValidationError(
                    f"Ensure this field has no more than "
                    f"{self._HEADER_TEXT_MAX_LENGTH} characters when the header is text."
                )
        return value

    def validate_template_footer(self, value: str | None) -> str | None:
        value = _normalize_blank_footer(value)
        if value and len(value) > self._FOOTER_MAX_LENGTH:
            raise serializers.ValidationError(
                f"Ensure this field has no more than {self._FOOTER_MAX_LENGTH} characters."
            )
        return value

    def validate_template_button(self, value: list) -> list:
        if not value:
            return value

        url_buttons = [b for b in value if b.get("type") == self._URL_BUTTON_TYPE]
        quick_replies = [
            b for b in value if b.get("type") == self._QUICK_REPLY_BUTTON_TYPE
        ]

        if url_buttons and quick_replies:
            raise serializers.ValidationError(
                "Cannot mix URL and QUICK_REPLY buttons in a single sample."
            )

        if len(url_buttons) > self._MAX_URL_BUTTONS:
            raise serializers.ValidationError(
                f"At most {self._MAX_URL_BUTTONS} URL button is allowed."
            )

        if len(quick_replies) > self._MAX_QUICK_REPLY_BUTTONS:
            raise serializers.ValidationError(
                f"At most {self._MAX_QUICK_REPLY_BUTTONS} QUICK_REPLY buttons are allowed."
            )

        self._validate_button_text_lengths(value)

        return value

    def _validate_button_text_lengths(self, buttons: list) -> None:
        for button in buttons:
            text = button.get("text", "")
            if text and len(text) > self._BUTTON_TEXT_MAX_LENGTH:
                raise serializers.ValidationError(
                    f"Each button text must be at most "
                    f"{self._BUTTON_TEXT_MAX_LENGTH} characters."
                )

    def _is_plain_text_header(self, header: str) -> bool:
        """Return ``True`` only when the header is operator-typed text.

        Image headers (HTTP(S) URLs, base64 data URIs, S3 URLs) are
        exempt from the length cap. Reuses ``HeaderTransformer`` so
        the validation gate and wire-shape dispatch stay aligned.
        """
        transformer = HeaderTransformer()
        if header.startswith(("http://", "https://")):
            return False
        if transformer._is_base_64(header):
            return False
        return True
