from django.urls import path

from retail.api.features.views import FeaturesView

from .integrated_feature.views import (
    IntegratedFeatureSettingsView,
    IntegratedFeatureView,
)


urlpatterns = [
    path(
        "feature/<uuid:feature_uuid>/integrate/",
        IntegratedFeatureView.as_view(),
        name="integrated_feature",
    ),
    path("feature/<uuid:project_uuid>/", FeaturesView.as_view(), name="features"),
    path(
        "integrated_feature/<uuid:feature_uuid>/settings/",
        IntegratedFeatureSettingsView.as_view(),
        name="integrated-feature-settings",
    ),
    path(
        "integrated_feature/<uuid:project_uuid>/",
        IntegratedFeatureView.as_view(),
        name="integrated-features",
    ),
]
