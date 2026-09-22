import uuid as uuid_lib
from typing import Optional

from django.db import models
from django.core.cache import cache

from retail.agents.shared.cache import IntegratedAgentCacheHandlerRedis


class ActiveProjectManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class ActiveOnboardingManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class Project(models.Model):
    name = models.CharField(max_length=256)
    uuid = models.UUIDField(unique=True)
    organization_uuid = models.UUIDField(null=True)
    vtex_account = models.CharField(max_length=100, null=True, blank=True)
    language = models.CharField(max_length=64, null=True, blank=True)
    config = models.JSONField(default=dict)
    is_blocked = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_live_desk_copilot = models.BooleanField(default=False)
    parent_project = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="copilot_projects",
        null=True,
        blank=True,
    )
    modified_on = models.DateTimeField(auto_now=True)

    objects = ActiveProjectManager()
    all_objects = models.Manager()

    def __str__(self) -> str:
        return f"{self.name} [VTEX] {self.vtex_account}"

    class Meta:
        default_manager_name = "objects"
        base_manager_name = "all_objects"
        indexes = [
            models.Index(fields=["uuid"]),
            models.Index(fields=["vtex_account"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(is_live_desk_copilot=False, parent_project__isnull=True)
                    | models.Q(is_live_desk_copilot=True, parent_project__isnull=False)
                ),
                name="projects_project_copilot_requires_parent",
            ),
        ]

    def clear_cache(self) -> None:
        """
        Clears all cache entries related to this project.
        Should be called after updates to VTEX account or related fields.
        """
        copilot_uuids = Project.all_objects.filter(parent_project=self).values_list(
            "uuid", flat=True
        )
        uuids_to_clear = [self.uuid, *copilot_uuids]
        for project_uuid in uuids_to_clear:
            if project_uuid:
                cache.delete(f"project_domain_{project_uuid}")
                cache.delete(f"project_by_uuid_{project_uuid}")
                cache.delete(f"project_vtex_context_{project_uuid}")
        if self.vtex_account:
            cache.delete(f"project_by_vtex_account_{self.vtex_account}")

    def resolve_vtex_account(self) -> Optional[str]:
        """Return the VTEX account used for proxy calls.

        Live desk copilots inherit the account from ``parent_project``,
        which remains the source of truth.
        """
        source = self._vtex_account_source()
        if source is None:
            return None
        return source.vtex_account or None

    def _vtex_account_source(self) -> Optional["Project"]:
        """Return the project that owns the VTEX account.

        Uses ``all_objects`` so a soft-deleted parent still provides the
        account instead of disappearing behind the active-only manager.
        """
        if not self.is_live_desk_copilot:
            return self
        if not self.parent_project_id:
            return None
        try:
            return Project.all_objects.get(pk=self.parent_project_id)
        except Project.DoesNotExist:
            return None

    def clear_integrated_agents_cache(self) -> None:
        """
        Clears the IntegratedAgent webhook cache for every agent linked to
        this project. Used when a project-wide flag (e.g. is_blocked) changes
        and cached IntegratedAgent instances must re-read the new state.
        """
        IntegratedAgentCacheHandlerRedis().clear_cached_agents(
            self.integrated_agents.values_list("uuid", flat=True)
        )


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
    is_active = models.BooleanField(default=True, db_index=True)
    created_on = models.DateTimeField(auto_now_add=True)
    current_page = models.CharField(max_length=255, blank=True, default="")
    completed = models.BooleanField(default=False)
    failed = models.BooleanField(default=False)
    skipped = models.BooleanField(default=False)
    progress = models.IntegerField(default=0)
    current_step = models.CharField(max_length=50, blank=True, default="")
    crawler_result = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        default=None,
    )
    config = models.JSONField(default=dict, blank=True)

    objects = ActiveOnboardingManager()
    all_objects = models.Manager()

    class Meta:
        default_manager_name = "objects"
        base_manager_name = "all_objects"
        constraints = [
            models.UniqueConstraint(
                fields=["vtex_account"],
                condition=models.Q(is_active=True),
                name="projects_onboarding_unique_active_vtex_account",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Onboarding [{self.vtex_account}] "
            f"step={self.current_step} progress={self.progress}% "
            f"current_page={self.current_page}, completed={self.completed}"
        )
