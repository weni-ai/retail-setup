from rest_framework import serializers

from retail.metrics.constants import PRODUCT_METRIC_EVENT_TYPES, SUGGESTED_PLANS


class RecordProductMetricEventSerializer(serializers.Serializer):
    """Validates the client-supplied portion of a product metric click.

    Identity, time, country, and project are resolved on the server.
    ``user_email`` and ``vtex_account`` are never accepted from the body.
    """

    event_type = serializers.ChoiceField(choices=PRODUCT_METRIC_EVENT_TYPES)
    suggested_plan = serializers.ChoiceField(choices=SUGGESTED_PLANS, required=False)
