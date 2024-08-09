from django import forms

from .models import IntegratedFeature, FeatureVersion
from retail.integrations.models import Queue, Sector, Integration

class IntegrateFeatureForm(forms.ModelForm):
    sector_name = forms.CharField(max_length=50)
    queue_name = forms.CharField(max_length=50)

    class Meta:
        model = IntegratedFeature
        fields = ["feature_version", "parameters", "sector_name", "queue_name"]
        labels = {"feature_version": "Versão"}

    def __init__(self, *args, **kwargs):
        feature = kwargs.pop("feature", None)
        super().__init__(*args, **kwargs)
        if feature:
            self.fields["feature_version"].queryset = FeatureVersion.objects.order_by(
                "-created_on"
            ).filter(feature=feature)

