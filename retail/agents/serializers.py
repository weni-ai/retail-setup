from rest_framework import serializers


class PushAgentSerializer(serializers.Serializer):
    project_uuid = serializers.UUIDField(required=True)
    agents = serializers.JSONField(required=True)


class ReadAgentSerializer(serializers.Serializer):
    name = serializers.CharField()
    is_oficial = serializers.CharField()
    lambda_arn = serializers.CharField()
