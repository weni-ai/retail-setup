from rest_framework import serializers


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


class AgentSerializer(serializers.Serializer):
    name = serializers.CharField()
    rules = serializers.DictField(child=RuleSerializer())
    pre_processing = PreProcessingSerializer(source="pre-processing", required=False)


class PushAgentSerializer(serializers.Serializer):
    project_uuid = serializers.UUIDField(required=True)
    agents = serializers.DictField(child=AgentSerializer(), required=True)


class PreApprovedTemplateSerializer(serializers.Serializer):
    name = serializers.CharField()
    content = serializers.CharField(allow_null=True)
    is_valid = serializers.BooleanField(allow_null=True)


class ReadAgentSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    is_oficial = serializers.BooleanField()
    lambda_arn = serializers.CharField()
    templates = PreApprovedTemplateSerializer(many=True)


class ReadIntegratedAgentSerializer(serializers.Serializer):
    agent = ReadAgentSerializer()
    webhook_uuid = serializers.CharField()
    client_secret = serializers.CharField()

    def __init__(self, *args, show_client_secret=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not show_client_secret:
            self.fields.pop("client_secret")
