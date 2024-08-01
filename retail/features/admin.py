from django.contrib import admin
from django import forms

from retail.features.models import Feature, FeatureVersion, IntegratedFeature, Brain

class FeatureVersionInlineForm(forms.ModelForm):
    class Meta:
        model = FeatureVersion
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["brain"].required = False


class FeatureVersionInline(admin.StackedInline):
    model = FeatureVersion
    form = FeatureVersionInlineForm
    extra = 0

class FeatureAdmin(admin.ModelAdmin):
    inlines = [FeatureVersionInline]

admin.site.register(Feature, FeatureAdmin)
admin.site.register(Brain)