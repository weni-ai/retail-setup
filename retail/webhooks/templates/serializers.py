from rest_framework import serializers


class TemplateStatusSerializer(serializers.Serializer):
    """
    Serializer for template status webhook data.
    Validates the incoming webhook payload for template status updates.
    """

    app_uuid = serializers.UUIDField(required=True)
    template_statuses = serializers.DictField(
        child=serializers.CharField(), required=True
    )
