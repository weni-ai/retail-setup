from rest_framework import serializers


class OrdersQueryParamsSerializer(serializers.Serializer):
    """
    Validates that raw_query is provided.
    The raw_query contains the filter parameters to be passed to the VTEX API.
    """

    raw_query = serializers.CharField(required=True)


class OrderFormTrackingSerializer(serializers.Serializer):
    """Input payload for linking a VTEX order-form to a WhatsApp channel."""

    order_form_id = serializers.CharField(max_length=128, required=True)
    channel_uuid = serializers.UUIDField(required=True)


class CreateProjectUserSerializer(serializers.Serializer):
    """Validates the payload for creating a project via the IO proxy."""

    user_email = serializers.EmailField(required=True)


class VtexProxySerializer(serializers.Serializer):
    """
    Validates the payload for VTEX proxy requests.

    This serializer validates the method, path, and optional parameters
    to be forwarded to VTEX IO proxy endpoint.
    """

    method = serializers.ChoiceField(
        choices=["GET", "POST", "PUT", "PATCH"], required=True
    )
    path = serializers.CharField(required=True)
    headers = serializers.DictField(required=False, allow_null=True)
    data = serializers.JSONField(required=False, allow_null=True)
    params = serializers.DictField(required=False, allow_null=True)


class LeadSerializer(serializers.Serializer):
    """Validates the payload for registering a sales lead from a VTEX account."""

    user = serializers.EmailField(required=True)
    plan = serializers.CharField(max_length=100, required=True)
    vtex_account = serializers.CharField(max_length=100, required=True)
    data = serializers.DictField(required=False, default=dict)
