from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=256)
    uuid = models.UUIDField()
    organization_name = models.CharField(max_length=256)

    def __str__(self) -> str:
        return self.name
