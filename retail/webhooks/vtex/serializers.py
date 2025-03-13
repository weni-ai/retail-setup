from rest_framework import serializers


class CartSerializer(serializers.Serializer):
    """
    Serializer to validate cart data received from VTEX.
    """
    account = serializers.CharField()
    cart_id = serializers.CharField()
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
    vtexAccount = serializers.CharField()
