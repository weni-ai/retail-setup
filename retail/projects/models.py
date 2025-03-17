from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=256)
    uuid = models.UUIDField()
    organization_uuid = models.UUIDField(null=True)
    vtex_account = models.CharField(max_length=100, null=True, blank=True)
    config = models.JSONField(default=dict)

    def __str__(self) -> str:
        return self.name
