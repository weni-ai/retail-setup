from django.contrib import admin
from django import forms

from retail.features.models import Feature, FeatureVersion, IntelligentAgent
from retail.event_driven import eda_publisher


class FeatureVersionInlineForm(forms.ModelForm):
    class Meta:
        model = FeatureVersion
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["IntelligentAgent"].required = False

    def save(self, commit) -> FeatureVersion:
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

        return feature_version


class IntelligentAgentInline(admin.StackedInline):
    model = IntelligentAgent
    extra = 0


class FeatureVersionInline(admin.StackedInline):
    model = FeatureVersion
    form = FeatureVersionInlineForm
    extra = 0


class FeatureAdmin(admin.ModelAdmin):
    search_fields = ["name", "uuid"]
    list_filter = ["category"]
    inlines = [FeatureVersionInline]


admin.site.register(Feature, FeatureAdmin)
admin.site.register(IntelligentAgent)
admin.site.register(FeatureVersion)
