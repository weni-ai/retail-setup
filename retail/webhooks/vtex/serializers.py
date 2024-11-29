from rest_framework import serializers


class CartSerializer(serializers.Serializer):
    """
    Serializer to validate cart data received from VTEX.
    """

    action = serializers.ChoiceField(choices=["create", "update", "purchased", "empty"])
    account = serializers.CharField()
    homePhone = serializers.CharField()
    cart_url = serializers.CharField()
