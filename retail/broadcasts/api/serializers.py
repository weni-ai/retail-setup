"""DRF serializers for broadcast dispatch and summary report APIs."""

from rest_framework import serializers

from retail.broadcasts.usecases.list_broadcast_dispatches import BroadcastDispatchRow


class _DateRangeQuerySerializer(serializers.Serializer):
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)

    def validate(self, attrs):
        if attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError(
                "start_date must be on or before end_date."
            )
        return attrs


class ListBroadcastDispatchesQuerySerializer(_DateRangeQuerySerializer):
    """Query params for the paginated dispatch report."""

    page = serializers.IntegerField(required=False, default=1, min_value=1)
    page_size = serializers.IntegerField(required=False, default=20, min_value=1)


class GetBroadcastSummaryQuerySerializer(_DateRangeQuerySerializer):
    """Query params for the consolidated delivered/converted report."""


class BroadcastDispatchRowSerializer(serializers.Serializer):
    contact_urn = serializers.CharField()
    order_id = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    converted = serializers.BooleanField()
    dispatched_at = serializers.DateTimeField()
    converted_at = serializers.DateTimeField(allow_null=True)

    def to_representation(self, instance: BroadcastDispatchRow) -> dict:
        return {
            "contact_urn": instance.contact_urn,
            "order_id": instance.order_id,
            "status": instance.status,
            "converted": instance.converted,
            "dispatched_at": instance.dispatched_at,
            "converted_at": instance.converted_at,
        }


class BroadcastSummarySerializer(serializers.Serializer):
    delivered = serializers.IntegerField()
    converted = serializers.IntegerField()

    def to_representation(self, instance) -> dict:
        return {
            "delivered": instance.delivered,
            "converted": instance.converted,
        }


class GetPaymentRecoveryConversionMetricsQuerySerializer(_DateRangeQuerySerializer):
    """Query params for payment recovery conversion metrics."""


class PaymentRecoveryConversionMetricsSerializer(serializers.Serializer):
    total_dispatches = serializers.IntegerField()
    converted_payments = serializers.IntegerField()
    conversion_rate = serializers.DecimalField(max_digits=7, decimal_places=2)
    recovered_revenue = serializers.DecimalField(max_digits=14, decimal_places=2)
    average_ticket = serializers.DecimalField(
        max_digits=14, decimal_places=2, allow_null=True
    )
    first_conversion_at = serializers.DateTimeField(allow_null=True)
    last_conversion_at = serializers.DateTimeField(allow_null=True)

    def to_representation(self, instance) -> dict:
        return {
            "total_dispatches": instance.total_dispatches,
            "converted_payments": instance.converted_payments,
            "conversion_rate": instance.conversion_rate,
            "recovered_revenue": instance.recovered_revenue,
            "average_ticket": instance.average_ticket,
            "first_conversion_at": instance.first_conversion_at,
            "last_conversion_at": instance.last_conversion_at,
        }
