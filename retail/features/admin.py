from django.contrib import admin
from django import forms

from retail.features.models import Feature, FeatureVersion, IntelligentAgent
from retail.event_driven import eda_publisher


class FeatureVersionInlineForm(forms.ModelForm):
    class Meta:
        model = FeatureVersion
        fields = ["definition", "parameters", "version", "IntelligentAgent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["IntelligentAgent"].required = False

    def save(self, commit: bool) -> FeatureVersion:
        feature_version: FeatureVersion = super().save(commit)
        agent = feature_version.IntelligentAgent

        if agent is not None:
            message_body = dict(
                uuid=str(agent.uuid),
                feature_version_uuid=str(feature_version.uuid),
                brain=dict(
                    agent=dict(
                        name=agent.name,
                        role=agent.role,
                        personality=agent.personality,
                        instructions=agent.instructions,
                        goal=agent.goal,
                    ),
                    instructions=agent.instructions,
                    actions=agent.actions,
                ),
            )

            eda_publisher.send_message(message_body, "feature-version.topic")


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
                        "uuid": queue["uuid"],
                        "name": queue["name"],
                        "agents": [""]
                    })
            sectors_base.append({
                "manager_email": [""],
                "working_hours": {"init": "", "close": ""},
                "service_limit": 0,
                "tags": [""],
                "name": sector["name"],
                "uuid": sector["uuid"],
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


class intelligencAgentAdmin(admin.ModelAdmin):
    search_fields = ["name", "uuid"]


admin.site.register(Feature, FeatureAdmin)
admin.site.register(IntelligentAgent, intelligencAgentAdmin)
