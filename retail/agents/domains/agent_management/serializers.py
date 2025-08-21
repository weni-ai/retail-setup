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
    result_example = serializers.JSONField(required=False, allow_null=True)

    def validate_result_example(self, value):
        if value is None:
            return value

        if not isinstance(value, list):
            raise serializers.ValidationError("Examples must be a list of objects")

        for i, example in enumerate(value):
            if not isinstance(example, dict):
                raise serializers.ValidationError(
                    f"Example at index {i} must be an object (dictionary)"
                )

            if "urn" not in example:
                raise serializers.ValidationError(
                    f"Example at index {i} must have 'urn' key"
                )

            if not isinstance(example["urn"], str):
                raise serializers.ValidationError(
                    f"Example at index {i}: 'urn' must be a string"
                )

            if "data" not in example:
                raise serializers.ValidationError(
                    f"Example at index {i} must have 'data' key"
                )

            if not isinstance(example["data"], dict):
                raise serializers.ValidationError(
                    f"Example at index {i}: 'data' must be a dictionary"
                )

        return value


class PushAgentsCredentialSerializer(serializers.Serializer):
    key = serializers.CharField(required=True)
    label = serializers.CharField(required=False, allow_null=True)
    placeholder = serializers.CharField(required=False, allow_null=True)
    is_confidential = serializers.BooleanField(required=False, default=False)


class AgentSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    rules = serializers.DictField(child=RuleSerializer())
    pre_processing = PreProcessingSerializer(required=False)
    credentials = PushAgentsCredentialSerializer(many=True)
    language = serializers.CharField()


class PushAgentSerializer(serializers.Serializer):
    project_uuid = serializers.UUIDField(required=True)
    agents = serializers.DictField(child=AgentSerializer(), required=True)


class ReadAgentSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    description = serializers.CharField()
    language = serializers.CharField()
    is_oficial = serializers.BooleanField()
    templates = serializers.SerializerMethodField()
    examples = serializers.JSONField()

    def get_templates(self, obj):
        templates = obj.templates.all()
        return PreApprovedTemplateSerializer(templates, many=True).data


class GalleryAgentSerializer(ReadAgentSerializer):
    assigned = serializers.SerializerMethodField("get_is_assigned")
    assigned_agent_uuid = serializers.SerializerMethodField("get_assigned_agent_uuid")
    credentials = serializers.JSONField()

    def get_is_assigned(self, obj) -> bool:
        project_uuid = self.context.get("project_uuid")
        return obj.integrateds.filter(
            project__uuid=project_uuid, is_active=True
        ).exists()

    def get_assigned_agent_uuid(self, obj):
        project_uuid = self.context.get("project_uuid")
        assigned = obj.integrateds.filter(
            project__uuid=project_uuid, is_active=True
        ).first()

        if not assigned:
            return None

        return str(assigned.uuid)


class PreApprovedTemplateSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    content = serializers.CharField(allow_null=True)
    start_condition = serializers.CharField()
    display_name = serializers.CharField()
    is_valid = serializers.BooleanField(allow_null=True)
    metadata = serializers.JSONField()
