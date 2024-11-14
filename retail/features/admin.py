import json
import re

from django.contrib import admin
from django import forms
from django.db.models.query import QuerySet
from django.http import HttpRequest

from retail.features.models import Feature, FeatureVersion
from retail.features.forms import FeatureForm, FunctionForm


class FeatureVersionInlineForm(forms.ModelForm):
    class Meta:
        model = FeatureVersion
        fields = [
            "definition",
            "version",
            "action_types",
            "action_name",
            "action_prompt",
            "action_base_flow_name",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean_definition(self):
        definition = self.cleaned_data.get("definition")

        flows = definition.get("flows")
        if not flows:
            raise forms.ValidationError(
                "O atributo 'flows' é obrigatório e não foi encontrado no JSON."
            )

        flows_name = []

        for flow in flows:
            if flow.get("name") in flows_name:
                raise forms.ValidationError(
                    "Não é possivel ter mais de um fluxo com o mesmo nome"
                )
            flows_name.append(flow.get("name"))

            nodes = flow.get("nodes", [])
            for node in nodes:
                actions = node.get("actions", [])
                for action in actions:
                    if action.get("type") == "open_ticket" and action.get("assignee"):
                        raise forms.ValidationError(
                            "O campo 'assignee' não pode ser preenchido em actions do tipo 'open_ticket'."
                        )

        return definition
    
    def clean_action_base_flow_name(self):
        action_base_flow_name = self.cleaned_data.get("action_base_flow_name", None)
        if action_base_flow_name is None:
            return action_base_flow_name
        definition = self.cleaned_data.get("definition")
        if definition is None:
            raise forms.ValidationError("Você precisa colocar uma definition")
        error_message = "você tem de digitar um nome de fluxo existente na sua definition, são eles: "
        for flow in definition.get("flows"):
            error_message += "\n" + flow.get("name")
            if flow.get("name") == action_base_flow_name:
                return action_base_flow_name
        raise forms.ValidationError(error_message)

    def save(self, commit: bool) -> FeatureVersion:
        feature_version: FeatureVersion = super().save(commit)
        feature = feature_version.feature

        feature.feature_type = "FEATURE"
        feature.save()

        matches = re.findall(
            r"globals\.([a-zA-Z_]+)", json.dumps(self.instance.definition)
        )
        for match in matches:
            if match not in self.instance.globals_values:
                self.instance.globals_values.append(match)
        self.instance.save()

        flows = self.instance.definition.get("flows", [])
        sectors = []
        for flow in flows:
            if len(flow["integrations"]["ticketers"]) > 0:
                for ticketer in flow["integrations"]["ticketers"]:
                    sectors.append(ticketer)
            if flow.get("name") == self.instance.action_base_flow_name:
                self.instance.action_base_flow_uuid = flow.get("uuid")

        sectors_base = []
        for sector in sectors:
            queues = []
            if "queues" in sector:
                for queue in sector["queues"]:
                    queues.append(
                        {
                            "name": queue["name"],
                        }
                    )
            sectors_base.append(
                {"name": sector["name"], "tags": [""], "queues": queues}
            )

        self.instance.sectors = sectors_base
        self.instance.save()
        return feature_version


class FeatureVersionInline(admin.StackedInline):
    model = FeatureVersion
    form = FeatureVersionInlineForm
    extra = 0


class FeatureAdmin(admin.ModelAdmin):
    search_fields = ["name", "uuid"]
    inlines = [FeatureVersionInline]
    form = FeatureForm

    def get_queryset(self, request):
        feature_queryset = super().get_queryset(request)
        return feature_queryset.filter(feature_type="FEATURE")


class Function(Feature):
    class Meta:
        proxy = True


class FunctionVersionInlineForm(forms.ModelForm):
    class Meta:
        model = FeatureVersion
        fields = [
            "definition",
            "version",
            "action_types",
            "action_name",
            "action_prompt",
            "action_base_flow_name",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean_definition(self):
        definition = self.cleaned_data.get("definition")
        flows = definition.get("flows")
        if not flows:
            raise forms.ValidationError(
                "O atributo 'flows' é obrigatório e não foi encontrado no JSON."
            )

        flows_name = []

        for flow in flows:
            if flow.get("name") in flows_name:
                raise forms.ValidationError(
                    "Não é possivel ter mais de um fluxo com o mesmo nome"
                )
            flows_name.append(flow.get("name"))

            nodes = flow.get("nodes", [])
            for node in nodes:
                actions = node.get("actions", [])
                for action in actions:
                    if action.get("type") == "open_ticket" and action.get("assignee"):
                        raise forms.ValidationError(
                            "O campo 'assignee' não pode ser preenchido em actions do tipo 'open_ticket'."
                        )

        return definition
    
    def clean_action_base_flow_name(self):
        action_base_flow_name = self.cleaned_data.get("action_base_flow_name", None)
        if action_base_flow_name is None:
            return action_base_flow_name
        definition = self.cleaned_data.get("definition")
        if definition is None:
            raise forms.ValidationError("Você precisa colocar uma definition")
        error_message = "você tem de digitar um nome de fluxo existente na sua definition, são eles: "
        for flow in definition.get("flows"):
            error_message += "\n" + flow.get("name")
            if flow.get("name") == action_base_flow_name:
                return action_base_flow_name
        raise forms.ValidationError(error_message)

    def save(self, commit: bool) -> FeatureVersion:
        feature_version: FeatureVersion = super().save(commit)

        feature = feature_version.feature
        feature.feature_type = "FUNCTION"
        feature.save()

        matches = re.findall(
            r"globals\.([a-zA-Z_]+)", json.dumps(self.instance.definition)
        )
        for match in matches:
            if match not in self.instance.globals_values:
                self.instance.globals_values.append(match)

        self.instance.save()

        flows = self.instance.definition.get("flows", [])
        sectors = []
        for flow in flows:
            if len(flow["integrations"]["ticketers"]) > 0:
                for ticketer in flow["integrations"]["ticketers"]:
                    sectors.append(ticketer)
            if flow.get("name") == self.instance.action_base_flow_name:
                self.instance.action_base_flow_uuid = flow.get("uuid")

        sectors_base = []
        for sector in sectors:
            queues = []
            if "queues" in sector:
                for queue in sector["queues"]:
                    queues.append(
                        {
                            "name": queue["name"],
                        }
                    )
            sectors_base.append(
                {"name": sector["name"], "tags": [""], "queues": queues}
            )

        self.instance.sectors = sectors_base
        self.instance.save()
        return feature_version


class FunctionVersionInline(admin.StackedInline):
    model = FeatureVersion
    form = FunctionVersionInlineForm
    extra = 0


class FunctionAdmin(admin.ModelAdmin):
    search_fields = ["name", "uuid"]
    inlines = [FunctionVersionInline]
    form = FunctionForm

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return self.model.objects.filter(feature_type="FUNCTION")


admin.site.register(Feature, FeatureAdmin)
admin.site.register(Function, FunctionAdmin)
