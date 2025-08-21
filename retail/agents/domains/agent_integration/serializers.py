from rest_framework import serializers

from django.conf import settings

from retail.templates.serializers import ReadTemplateSerializer


class RetrieveIntegratedAgentQueryParamsSerializer(serializers.Serializer):
    show_all = serializers.BooleanField(required=False, default=False)
    start = serializers.DateField(required=False, default=None)
    end = serializers.DateField(required=False, default=None)


class UpdateIntegratedAgentSerializer(serializers.Serializer):
    contact_percentage = serializers.IntegerField(required=False)
    global_rule = serializers.CharField(required=False, allow_null=True)


class ReadIntegratedAgentSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    channel_uuid = serializers.UUIDField()
    templates = serializers.SerializerMethodField("get_templates")
    webhook_url = serializers.SerializerMethodField("get_webhook_url")
    description = serializers.SerializerMethodField("get_description")
    contact_percentage = serializers.IntegerField()
    global_rule_prompt = serializers.CharField()

    def get_webhook_url(self, obj):
        domain_url = settings.DOMAIN
        return f"{domain_url}/api/v3/agents/webhook/{str(obj.uuid)}/"

    def get_description(self, obj):
        return obj.agent.description

    def get_templates(self, obj):
        return ReadTemplateSerializer(obj.templates.all(), many=True).data
