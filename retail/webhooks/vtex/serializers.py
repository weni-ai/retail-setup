from rest_framework import serializers


class CartSerializer(serializers.Serializer):
    """Validate cart data received from VTEX.

    The tenant (``vtex_account``) is not read from the body; it comes from the
    authenticated context (``self.auth``).
    """

    cart_id = serializers.CharField()
    phone = serializers.CharField()
    name = serializers.CharField()


class ExternalAbandonedCartSerializer(serializers.Serializer):
    """Validate abandoned cart payloads from external webhook callers."""

    order_form_id = serializers.CharField()
    phone = serializers.CharField()
    name = serializers.CharField()


class OrderStatusSerializer(serializers.Serializer):
    recorder = serializers.JSONField()
    domain = serializers.CharField()
    orderId = serializers.CharField()
    currentState = serializers.CharField()
    lastState = serializers.CharField()
    currentChangeDate = serializers.DateTimeField()
    lastChangeDate = serializers.DateTimeField()
