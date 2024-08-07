from django import forms
import json


class DynamicParamsField(forms.Field):
    def __init__(self, *args, param_list=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.param_list = param_list or []

    def widget_attrs(self, widget):
        return {
            **super().widget_attrs(widget),
            "data-param-list": json.dumps(self.param_list),
        }

    def to_python(self, value):
        if not value:
            return {}
        return json.loads(value)

    def validate(self, value):
        super().validate(value)
        if not isinstance(value, dict):
            raise forms.ValidationError("Invalid format")
