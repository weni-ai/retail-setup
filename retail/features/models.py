import uuid

from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

from retail.projects.models import Project


class Feature(models.Model):

    features_types_choices = [("FEATURE", "Feature"), ("FUNCTION", "Function")]
    categories_choices = [("ACTIVE", "Active"), ("PASSIVE", "Passive")]

    created_on = models.DateTimeField(
        "when are created the new feature", auto_now_add=True
    )
    description = models.TextField(null=True)
    name = models.CharField(max_length=256)
    uuid = models.UUIDField(
        "UUID", primary_key=True, default=uuid.uuid4, editable=False
    )
    feature_type = models.CharField(
        max_length=100, choices=features_types_choices, default="FEATURE"
    )
    functions = models.ManyToManyField("self", null=True)
    category = models.CharField(
        max_length=100, choices=categories_choices, default="PASSIVE"
    )
    documentation_url = models.TextField(null=True)
    disclaimer = models.TextField(null=True)

    def __str__(self):
        return self.name

    @property
    def last_version(self):
        return self.versions.order_by("created_on").last()


class FeatureVersion(models.Model):
    ACTION_TYPES_CHOICES = [
        ("PERSONALIZADO", "Personalizado"),
        ("VOLTAR AO MENU", "Voltar ao Menu"),
        ("INTEGRAÇÕES GERAIS", "Interações gerais"),
        ("CONFIGURAR COMUNICAÇÕES", "Configurar comunicações"),
        ("DESPEDIDA", "Despedida"),
        ("SAC/FALE CONOSCO", "SAC/Fale conosco"),
        ("INDIQUE E GANHE", "Indique e Ganhe"),
        ("TROCA E DEVOLUÇÃO", "Troca e Devolução"),
        ("STATUS DO PEDIDO", "Status do Pedido"),
    ]

    uuid = models.UUIDField(
        "UUID", primary_key=True, default=uuid.uuid4, editable=False
    )

    definition = models.JSONField()
    globals_values = models.JSONField(null=True, blank=True, default=[])
    sectors = models.JSONField(null=True, blank=True)
    version = models.CharField(max_length=10, default="1.0")
    feature = models.ForeignKey(
        Feature, models.CASCADE, related_name="versions", null=True, blank=True
    )
    action_name = models.CharField(max_length=256, null=True, blank=True)
    action_prompt = models.TextField(null=True, blank=True)
    action_types = models.TextField(
        null=True, blank=True, choices=ACTION_TYPES_CHOICES, default="PERSONALIZADO"
    )
    action_type_brain = models.TextField(null=True, blank=True)

    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.version

    def get_flows_base(self):
        actions = []
        flows = self.definition.get("flows", [])
        for flow in flows:
            actions.append(
                {"flow_uuid": flow.get("uuid", ""), "flow_name": flow.get("name", "")}
            )
        return actions

    @property
    def get_action_types(self):
        return settings.ACTION_TYPES

    def save(self, *args) -> None:
        if self.action_types != "PERSONALIZADO" and self.action_types != None:
            for action_type in self.get_action_types:
                if self.action_types.lower() == action_type.get("name").lower():
                    self.action_name = action_type.get("name")
                    self.action_prompt = action_type.get("display_prompt")
                    self.action_type_brain = action_type.get("action_type")
                    break
        return super().save(*args)


class IntegratedFeature(models.Model):
    uuid = models.UUIDField(
        "UUID", primary_key=True, default=uuid.uuid4, editable=False
    )

    feature_version = models.ForeignKey(
        FeatureVersion, on_delete=models.CASCADE, related_name="integrated_features"
    )
    feature = models.ForeignKey(
        Feature, on_delete=models.CASCADE, related_name="integrated_features"
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="integrated_features"
    )
    globals_values = models.JSONField(null=True, default=dict, blank=True)
    sectors = models.JSONField(null=True, default=dict, blank=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="integrated_features"
    )
    integrated_on = models.DateField(auto_now_add=True)

    # def save(self, *args) -> None:
        # self.feature = self.feature_version.feature
        # return super().save(*args)

    def __str__(self) -> str:
        return self.feature_version.feature.name


class Flow(models.Model):
    uuid = models.UUIDField()
    flow_uuid = models.CharField(max_length=100, null=True)
    name = models.CharField(max_length=256)
    definition = models.JSONField()
    integrated_feature = models.ForeignKey(
        IntegratedFeature, on_delete=models.CASCADE, related_name="flows"
    )
