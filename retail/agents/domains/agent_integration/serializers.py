from rest_framework import serializers

from django.conf import settings

from retail.templates.serializers import ReadTemplateSerializer


class DevEnvironmentConfigSerializer(serializers.Serializer):
    """Serializer for development environment configuration."""

    phone_numbers = serializers.ListField(
        child=serializers.CharField(max_length=20), required=False, allow_empty=True
    )
    is_dev_mode = serializers.BooleanField(required=False, default=False)


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
    dev_environment_config = serializers.SerializerMethodField(
        "get_dev_environment_config"
    )

    def get_webhook_url(self, obj):
        domain_url = settings.DOMAIN
        return f"{domain_url}/api/v3/agents/webhook/{str(obj.uuid)}/"

    def get_description(self, obj):
        return obj.agent.description

    def get_templates(self, obj):
        return ReadTemplateSerializer(obj.templates.all(), many=True).data

    def get_dev_environment_config(self, obj):
        """Get development environment configuration from agent config."""
        dev_config = obj.config.get(
            "dev_environment", {"phone_numbers": [], "is_dev_mode": False}
        )
        return DevEnvironmentConfigSerializer(dev_config).data
