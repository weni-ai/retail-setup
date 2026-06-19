from rest_framework import serializers


ALLOWED_AGENT_TYPES = ("abandoned_cart", "order_status", "payment_recovery")


class AgentActiveQuerySerializer(serializers.Serializer):
    """Validates the ``agent`` query param, single or repeated.

    Accepts the param once (``?agent=order_status``) or repeated
    (``?agent=order_status&agent=payment_recovery``). The deserialized
    value is always a list of valid agent types and the endpoint
    answers with OR semantics across the list.
    """

    agent = serializers.ListField(
        child=serializers.ChoiceField(choices=ALLOWED_AGENT_TYPES),
        min_length=1,
    )
