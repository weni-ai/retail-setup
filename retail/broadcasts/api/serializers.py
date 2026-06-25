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
