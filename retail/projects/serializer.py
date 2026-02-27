from rest_framework import serializers

from retail.projects.models import ProjectOnboarding


class ProjectSerializer(serializers.Serializer):
    """Serializer for Project model."""

    name = serializers.CharField(read_only=True)
    uuid = serializers.UUIDField(read_only=True)


class ProjectVtexConfigSerializer(serializers.Serializer):
    """Serializer to validate VTEX store type input."""

    vtex_store_type = serializers.CharField(required=True)


class StartOnboardingSerializer(serializers.Serializer):
    """Serializer to validate the start onboarding (crawl) request."""

    crawl_url = serializers.URLField(required=True)
    channel = serializers.ChoiceField(
        choices=["wwc", "wpp-cloud"],
    )


class CrawlerWebhookSerializer(serializers.Serializer):
    """Serializer to validate incoming crawler webhook events."""

    task_id = serializers.CharField(required=True)
    event = serializers.CharField(required=True)
    timestamp = serializers.CharField(required=True)
    url = serializers.CharField(required=True)
    progress = serializers.IntegerField(required=False, default=0)
    data = serializers.DictField(required=False, default=dict)


class OnboardingPatchSerializer(serializers.ModelSerializer):
    """Serializer for PATCH updates to ProjectOnboarding (front-end editable fields)."""

    class Meta:
        model = ProjectOnboarding
        fields = ["completed", "current_page"]


class ProjectOnboardingSerializer(serializers.Serializer):
    """Serializer for the ProjectOnboarding status response."""

    uuid = serializers.UUIDField(read_only=True)
    vtex_account = serializers.CharField(read_only=True)
    project_uuid = serializers.SerializerMethodField()
    current_page = serializers.CharField(read_only=True)
    completed = serializers.BooleanField(read_only=True)
    failed = serializers.BooleanField(read_only=True)
    progress = serializers.IntegerField(read_only=True)
    current_step = serializers.CharField(read_only=True)
    crawler_result = serializers.CharField(read_only=True, allow_null=True)
    config = serializers.JSONField(read_only=True)
    created_on = serializers.DateTimeField(read_only=True)

    def get_project_uuid(self, obj) -> str | None:
        if obj.project is not None:
            return str(obj.project.uuid)
        return None
