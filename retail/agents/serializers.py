from typing import TYPE_CHECKING

from django.conf import settings
from rest_framework import serializers

from retail.templates.serializers import ReadTemplateSerializer

if TYPE_CHECKING:
    from .models import Agent


class SourceSerializer(serializers.Serializer):
    entrypoint = serializers.CharField()
    path = serializers.CharField()


class RuleSerializer(serializers.Serializer):
    display_name = serializers.CharField()
    template = serializers.CharField()
    start_condition = serializers.CharField()
    source = SourceSerializer()


class PreProcessingSerializer(serializers.Serializer):
    source = SourceSerializer(required=False)
    result_examples_file = serializers.CharField(required=False, allow_blank=True)
    pre_result_examples_file = serializers.CharField(required=False, allow_blank=True)


class PushAgentsCredentialSerializer(serializers.Serializer):
    key = serializers.CharField(required=True)
    label = serializers.CharField(required=False, allow_null=True)
    placeholder = serializers.CharField(required=False, allow_null=True)
    is_confidential = serializers.BooleanField(required=False, default=False)


class AgentSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    rules = serializers.DictField(child=RuleSerializer())
    pre_processing = PreProcessingSerializer(source="pre-processing", required=False)
    credentials = PushAgentsCredentialSerializer(many=True)


class PushAgentSerializer(serializers.Serializer):
    project_uuid = serializers.UUIDField(required=True)
    agents = serializers.DictField(child=AgentSerializer(), required=True)


class PreApprovedTemplateSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    content = serializers.CharField(allow_null=True)
    start_condition = serializers.CharField()
    display_name = serializers.CharField()
    is_valid = serializers.BooleanField(allow_null=True)
    metadata = serializers.JSONField()


class ReadAgentSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    description = serializers.CharField()
    is_oficial = serializers.BooleanField()
    templates = serializers.SerializerMethodField()

    def get_templates(self, obj):
        templates = obj.templates.all()
        return PreApprovedTemplateSerializer(templates, many=True).data


class GalleryAgentSerializer(ReadAgentSerializer):
    assigned = serializers.SerializerMethodField("get_is_assigned")
    assigned_agent_uuid = serializers.SerializerMethodField("get_assigned_agent_uuid")
    credentials = serializers.JSONField()

    def get_is_assigned(self, agent: "Agent") -> bool:
        project_uuid = self.context.get("project_uuid")
        return agent.integrateds.filter(project__uuid=project_uuid).exists()

    def get_assigned_agent_uuid(self, agent: "Agent"):
        project_uuid = self.context.get("project_uuid")
        return agent.integrateds.filter(project__uuid=project_uuid).first()


class ReadIntegratedAgentSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    channel_uuid = serializers.UUIDField()
    templates = ReadTemplateSerializer(many=True)
    webhook_url = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField("get_description")

    def get_webhook_url(self, obj):
        domain_url = settings.DOMAIN
        return f"{domain_url}/api/v3/agents/webhook/{str(obj.uuid)}/"

    def get_description(self, obj):
        return obj.agent.description


class AgentWebhookSerializer(serializers.Serializer):
    webhook_uuid = serializers.UUIDField(required=True)
