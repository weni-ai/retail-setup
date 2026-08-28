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


class BackInStockShopperSerializer(serializers.Serializer):
    """One shopper in a back-in-stock batch.

    Array order is FIFO (index 0 subscribed first). ``phone`` is digits
    only. ``name`` and ``locale`` are optional.
    """

    phone = serializers.RegexField(regex=r"^\d+$")
    name = serializers.CharField(required=False, allow_blank=True, default="")
    locale = serializers.CharField(required=False, allow_blank=True, default="pt-BR")


class BackInStockNotificationSerializer(serializers.Serializer):
    """Validate a back-in-stock batch from VTEX IO.

    One SKU plus a non-empty shopper list. Tenant comes from the JWT,
    not the body. Extra keys such as ``account`` or ``project_id`` are
    ignored.
    """

    sku_id = serializers.CharField()
    shoppers = BackInStockShopperSerializer(many=True, allow_empty=False)


class OrderStatusSerializer(serializers.Serializer):
    recorder = serializers.JSONField()
    domain = serializers.CharField()
    orderId = serializers.CharField()
    currentState = serializers.CharField()
    lastState = serializers.CharField()
    currentChangeDate = serializers.DateTimeField()
    lastChangeDate = serializers.DateTimeField()
