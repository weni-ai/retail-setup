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


class DirectSendCategoryWebhookSerializer(serializers.Serializer):
    """
    Validates the inbound payload for the incorrect-category webhook.
    """

    project_uuid = serializers.UUIDField(required=True)
    app_uuid = serializers.UUIDField(required=True)
    template_name = serializers.CharField(required=True, allow_blank=False)
    template_category = serializers.CharField(required=True, allow_blank=False)
    template_correct_category = serializers.CharField(required=True, allow_blank=False)
