from rest_framework import serializers


class ProjectVtexConfigSerializer(serializers.Serializer):
    """Serializer to validate VTEX store type input."""

    vtex_store_type = serializers.CharField(required=True)
