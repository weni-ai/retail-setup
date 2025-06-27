from rest_framework import serializers


class OrdersQueryParamsSerializer(serializers.Serializer):
    """
    Serializer for validating query parameters for the Orders endpoint.
    Validates that project_uuid is a valid UUID and raw_query is provided.
    The project_uuid is used to determine the VTEX account domain,
    while raw_query contains the filter parameters to be passed to the VTEX API.
    """

    project_uuid = serializers.UUIDField(required=True)
    raw_query = serializers.CharField(required=True)


class CartClickSerializer(serializers.Serializer):
    """Input payload for linking a VTEX order-form to a Meta click-ID."""

    order_form_id = serializers.CharField(max_length=128)
    whatsapp_click_id = serializers.CharField(max_length=128)
