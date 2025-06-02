from django.db import models
from django.core.cache import cache


class Project(models.Model):
    name = models.CharField(max_length=256)
    uuid = models.UUIDField()
    organization_uuid = models.UUIDField(null=True)
    vtex_account = models.CharField(max_length=100, null=True, blank=True)
    config = models.JSONField(default=dict)

    def __str__(self) -> str:
        return self.name

    # TODO: Uncomment this when we have a way to create indexes in production
    # class Meta:
    #     indexes = [
    #         models.Index(fields=["uuid"]),
    #         models.Index(fields=["vtex_account"]),
    #     ]

    def clear_cache(self) -> None:
        """
        Clears all cache entries related to this project.
        Should be called after updates to VTEX account or related fields.
        """
        if self.uuid:
            cache.delete(f"project_domain_{self.uuid}")
        if self.vtex_account:
            cache.delete(f"project_by_vtex_account_{self.vtex_account}")
