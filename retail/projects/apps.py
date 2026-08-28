from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "retail.projects"

    def ready(self):
        """Register model signals after Django has populated the app registry."""
        from retail.projects import signals  # noqa: F401
