import uuid

from django.db import models

from retail.features.models import FeatureVersion


class Integration(models.Model):
    feature_version = models.ForeignKey(
        FeatureVersion, on_delete=models.CASCADE, related_name="feature_integration"
    )
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)


class Sector(models.Model):
    integration = models.ForeignKey(
        Integration, on_delete=models.CASCADE, related_name="sectors"
    )
    uuid = models.UUIDField()
    name = models.TextField()


class Queue(models.Model):
    uuid = models.UUIDField()
    name = models.TextField()
    integration_ticketer = models.ForeignKey(
        Sector, on_delete=models.CASCADE, related_name="queues"
    )


class Intelligence(models.Model):
    integration = models.ForeignKey(
        Integration, on_delete=models.CASCADE, related_name="intelligences"
    )
    uuid = models.UUIDField()
    name = models.TextField()
    repository_uuid = models.UUIDField()
