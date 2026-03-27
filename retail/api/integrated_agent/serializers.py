from rest_framework import serializers


AGENT_CHOICES = ["abandoned_cart", "order_notification"]


class SendTestTemplateSerializer(serializers.Serializer):
    contact_urns = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
    )
    agent = serializers.ChoiceField(choices=AGENT_CHOICES)
    variables = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        default=list,
    )
