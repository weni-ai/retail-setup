from django import forms

from .models import IntegratedFeature, FeatureVersion


class IntegrateFeatureForm(forms.ModelForm):
    class Meta:
        model = IntegratedFeature
        fields = ["feature_version", "parameters"]
        labels = {"feature_version": "Versão"}

    def __init__(self, *args, **kwargs):
        feature = kwargs.pop("feature", None)
        super().__init__(*args, **kwargs)
        if feature:
            self.fields["feature_version"].queryset = FeatureVersion.objects.order_by(
                "-created_on"
            ).filter(feature=feature)
