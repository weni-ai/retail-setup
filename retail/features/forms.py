from django import forms

from .models import IntegratedFeature, FeatureVersion, Feature

class IntegrateFeatureForm(forms.ModelForm):

    class Meta:
        model = IntegratedFeature
        fields = ["feature_version", "parameters", "sectors", "action_name", "action_prompt"]
        labels = {"feature_version": "Versão"}

    def __init__(self, *args, **kwargs):
        feature = kwargs.pop("feature", None)
        super().__init__(*args, **kwargs)
        if feature:
            self.fields["feature_version"].queryset = FeatureVersion.objects.order_by(
                "-created_on"
            ).filter(feature=feature)


class FeatureForm(forms.ModelForm):
    class Meta:
        model = Feature
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        feature = kwargs.get("instance", None)
        functions = Feature.objects.exclude(feature_type="FEATURE")
        if feature and feature.feature_type == "FUNCTION":
            functions = functions.exclude(uuid=feature.uuid)
        super().__init__(*args, **kwargs)
        self.fields["functions"].queryset = functions    
        self.fields["functions"].required = False
