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


class BackInStockSubscribeSerializer(serializers.Serializer):
    """Validate a storefront subscribe forwarded by VTEX IO.

    Tenant comes from the JWT, not the body. Extra keys such as
    ``account`` are ignored.
    """

    sku_id = serializers.CharField()
    phone = serializers.RegexField(regex=r"^\d+$")
    name = serializers.CharField()
    seller = serializers.CharField()
    sales_channel = serializers.CharField()
    locale = serializers.CharField(required=False, allow_blank=True, default="pt-BR")


class BackInStockStockChangeSerializer(serializers.Serializer):
    """Validate a catalog stock-change forwarded by VTEX IO.

    The event does not carry quantity, seller or trade policy. Tenant
    comes from the JWT, not the body.
    """

    sku_id = serializers.CharField()


class OrderStatusSerializer(serializers.Serializer):
    recorder = serializers.JSONField()
    domain = serializers.CharField()
    orderId = serializers.CharField()
    currentState = serializers.CharField()
    lastState = serializers.CharField()
    currentChangeDate = serializers.DateTimeField()
    lastChangeDate = serializers.DateTimeField()
