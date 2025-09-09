from rest_framework import serializers


class ProjectSerializer(serializers.Serializer):
    """Serializer for Project model."""

    name = serializers.CharField(read_only=True)
    uuid = serializers.UUIDField(read_only=True)


class ProjectVtexConfigSerializer(serializers.Serializer):
    """Serializer to validate VTEX store type input."""

    vtex_store_type = serializers.CharField(required=True)
