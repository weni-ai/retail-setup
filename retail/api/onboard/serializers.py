from rest_framework import serializers


class ActivateWebchatSerializer(serializers.Serializer):
    """Validates the payload for webchat script activation."""

    app_uuid = serializers.UUIDField(required=True)
    account_id = serializers.CharField(required=True, max_length=64)
