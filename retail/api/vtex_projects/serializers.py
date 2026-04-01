from rest_framework import serializers


ALLOWED_AGENT_TYPES = ("abandoned_cart", "order_status")


class AgentActiveQuerySerializer(serializers.Serializer):
    agent = serializers.ChoiceField(choices=ALLOWED_AGENT_TYPES)
