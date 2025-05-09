from django.db import models


class Agent(models.Model):
    name = models.CharField(max_length=255)
    is_oficial = models.BooleanField()
    lambda_arn = models.CharField(max_length=500)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="agents"
    )


class IntegratedAgent(models.Model):
    agent = models.ForeignKey(
        "Agent", on_delete=models.CASCADE, related_name="integrateds"
    )
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="integrated_agents"
    )
    external_id = models.TextField()
