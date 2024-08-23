from django.contrib import admin
from django import forms

from retail.features.models import Feature, FeatureVersion
from retail.event_driven import eda_publisher
from retail.features.forms import FeatureForm


class FeatureVersionInlineForm(forms.ModelForm):
    class Meta:
        model = FeatureVersion
        fields = ["definition", "parameters", "version"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save(self, commit: bool) -> FeatureVersion:
        feature_version: FeatureVersion = super().save(commit)

        flows = self.instance.definition["flows"]
        
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
                    queues.append({
                        "name": queue["name"],
                    })
            sectors_base.append({
                "name": sector["name"],
                "tags": [""],
                "queues": queues
            })
        self.instance.sectors = sectors_base
        self.instance.save()
        return feature_version


class FeatureVersionInline(admin.StackedInline):
    model = FeatureVersion
    form = FeatureVersionInlineForm
    extra = 0


class FeatureAdmin(admin.ModelAdmin):
    search_fields = ["name", "uuid"]
    list_filter = ["category"]
    inlines = [FeatureVersionInline]
    form = FeatureForm

admin.site.register(Feature, FeatureAdmin)
