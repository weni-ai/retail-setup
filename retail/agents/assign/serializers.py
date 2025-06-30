from django.conf import settings
from rest_framework import serializers

from retail.templates.serializers import ReadTemplateSerializer


class ReadIntegratedAgentSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    channel_uuid = serializers.UUIDField()
    templates = serializers.SerializerMethodField("get_templates")
    webhook_url = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField("get_description")
    contact_percentage = serializers.IntegerField()

    def get_webhook_url(self, obj):
        domain_url = settings.DOMAIN
        return f"{domain_url}/api/v3/agents/webhook/{str(obj.uuid)}/"

    def get_description(self, obj):
        return obj.agent.description

    def get_templates(self, obj):
        templates = obj.templates.filter(is_active=True)
        return ReadTemplateSerializer(templates, many=True).data


class UpdateIntegratedAgentSerializer(serializers.Serializer):
    contact_percentage = serializers.IntegerField()
