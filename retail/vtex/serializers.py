from rest_framework import serializers


class OrdersQueryParamsSerializer(serializers.Serializer):
    """
    Serializer for validating query parameters for the Orders endpoint.
    Validates that raw_query is provided.
    The raw_query contains the filter parameters to be passed to the VTEX API.
    """

    raw_query = serializers.CharField(required=True)


class OrderFormTrackingSerializer(serializers.Serializer):
    """Input payload for linking a VTEX order-form to a WhatsApp channel."""

    order_form_id = serializers.CharField(max_length=128, required=True)
    channel_uuid = serializers.UUIDField(required=True)
