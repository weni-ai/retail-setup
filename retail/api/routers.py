from django.urls import path
from rest_framework import routers

from .integrated_feature.views import IntegratedFeatureView


urlpatterns = [
    path(
        "feature/<uuid:feature_uuid>/integrate/",
        IntegratedFeatureView.as_view(),
        name="integrated_feature"
    )
]