import json
import re

from django.contrib import admin
from django import forms

from retail.features.models import Feature, FeatureVersion
from retail.features.forms import FeatureForm


class FeatureVersionInlineForm(forms.ModelForm):
    class Meta:
        model = FeatureVersion
        fields = [
            "definition",
            "version",
            "action_types",
            "action_name",
            "action_prompt",
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

    def save(self, commit: bool) -> FeatureVersion:
        feature_version: FeatureVersion = super().save(commit)
        feature = feature_version.feature
        definition_text = json.dumps(self.instance.definition)
        for word in definition_text.split(" "):
            globals_values = []
            matches = re.findall(r'@globals\.([a-zA-Z_]+)', word)
            for match in matches:
                if match not in self.instance.globals_values:
                    self.instance.globals_values.append(match)
        self.instance.save()

        if feature.feature_type == "FEATURE":
            for feature_function in feature.functions.all():
                function_version = feature_function.versions.order_by(
                    "created_on"
                ).last()
                for flow in function_version.definition["flows"]:
                    self.instance.definition["flows"].append(flow)

                for campaign in function_version.definition["campaigns"]:
                    self.instance.definition["campaigns"].append(campaign)

                for trigger in function_version.definition["triggers"]:
                    self.instance.definition["triggers"].append(trigger)

                for field in function_version.definition["fields"]:
                    self.instance.definition["fields"].append(field)

                for group in function_version.definition["groups"]:
                    self.instance.definition["groups"].append(group)

                for globals_values in function_version.globals_values:
                    self.instance.globals_values.append(globals_values)
            self.instance.save()

        flows = self.instance.definition.get("flows", [])
        sectors = []
        for flow in flows:
            if len(flow["integrations"]["ticketers"]) > 0:
                for ticketer in flow["integrations"]["ticketers"]:
                    sectors.append(ticketer)

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


admin.site.register(Feature, FeatureAdmin)
