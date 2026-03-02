import uuid as uuid_lib

from django.db import models
from django.core.cache import cache


class Project(models.Model):
    name = models.CharField(max_length=256)
    uuid = models.UUIDField(unique=True)
    organization_uuid = models.UUIDField(null=True)
    vtex_account = models.CharField(max_length=100, null=True, blank=True)
    language = models.CharField(max_length=64, null=True, blank=True)
    config = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f"{self.name} [VTEX] {self.vtex_account}"

    class Meta:
        indexes = [
            models.Index(fields=["uuid"]),
            models.Index(fields=["vtex_account"]),
        ]

    def clear_cache(self) -> None:
        """
        Clears all cache entries related to this project.
        Should be called after updates to VTEX account or related fields.
        """
        if self.uuid:
            cache.delete(f"project_domain_{self.uuid}")
            cache.delete(f"project_by_uuid_{self.uuid}")
        if self.vtex_account:
            cache.delete(f"project_by_vtex_account_{self.vtex_account}")


class ProjectOnboarding(models.Model):
    """
    Tracks the full onboarding lifecycle for a store.

    Each step has its own progress (0-100%). Step names are
    defined by the consuming clients and are not enforced here.
    """

    SUCCESS = "SUCCESS"
    FAIL = "FAIL"

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    vtex_account = models.CharField(max_length=100, db_index=True)
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name="onboarding",
        null=True,
        blank=True,
    )
    created_on = models.DateTimeField(auto_now_add=True)
    current_page = models.CharField(max_length=255, blank=True, default="")
    completed = models.BooleanField(default=False)
    failed = models.BooleanField(default=False)
    progress = models.IntegerField(default=0)
    current_step = models.CharField(max_length=50, blank=True, default="")
    crawler_result = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        default=None,
    )
    config = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return (
            f"Onboarding [{self.vtex_account}] "
            f"step={self.current_step} progress={self.progress}% "
            f"current_page={self.current_page}, completed={self.completed}"
        )
