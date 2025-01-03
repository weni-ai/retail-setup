from rest_framework import serializers


class CartSerializer(serializers.Serializer):
    """
    Serializer to validate cart data received from VTEX.
    """

    account = serializers.CharField()
    cart_id = serializers.CharField()
