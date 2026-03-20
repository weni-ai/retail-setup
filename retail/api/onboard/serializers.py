from rest_framework import serializers


class ActivateWebchatSerializer(serializers.Serializer):
    """Validates the payload for webchat script activation."""

    app_uuid = serializers.UUIDField(required=True)
    account_id = serializers.CharField(required=True, max_length=64)


class ActivateWppCloudSerializer(serializers.Serializer):
    """Validates the payload for WPP Cloud channel activation."""

    project_uuid = serializers.UUIDField(required=True)
    percentage = serializers.IntegerField(required=True, min_value=0, max_value=100)
