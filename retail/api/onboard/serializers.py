from rest_framework import serializers


class ActivateWebchatSerializer(serializers.Serializer):
    """Validates the payload for webchat script activation.

    Neither the tenant (``vtex_account``) nor the ``account_id`` identity claim
    is read from the body; both come exclusively from the authenticated context
    (``self.auth``).
    """

    app_uuid = serializers.UUIDField(required=True)


class ActivateWppCloudSerializer(serializers.Serializer):
    """Validates the payload for WPP Cloud channel activation.

    The tenant (``project_uuid``) is never read from the body; it comes
    exclusively from the authenticated context (``self.auth``).
    """

    percentage = serializers.IntegerField(required=True, min_value=0, max_value=100)
