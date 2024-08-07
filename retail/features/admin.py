from django.contrib import admin
from django import forms

from retail.features.models import Feature, FeatureVersion, IntegratedFeature, IntelligentAgent

class FeatureVersionInlineForm(forms.ModelForm):
    class Meta:
        model = FeatureVersion
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["IntelligentAgent"].required = False

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


class IntegratedFeatureAdmin(admin.ModelAdmin):
    model = IntegratedFeature
    extra = 0

admin.site.register(Feature, FeatureAdmin)
admin.site.register(IntelligentAgent)
admin.site.register(FeatureVersion)
admin.site.register(IntegratedFeature, IntegratedFeatureAdmin)