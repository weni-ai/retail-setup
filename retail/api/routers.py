from django.urls import path

from retail.api.agents.views import AgentsView
from retail.api.features.views import FeaturesView

from .integrated_feature.views import (
    IntegratedFeatureSettingsView,
    IntegratedFeatureView,
    AppIntegratedFeatureView,
    NexusAgentIntegrationView,
)


urlpatterns = [
    path(
        "feature/<uuid:feature_uuid>/integrate/",
        IntegratedFeatureView.as_view(),
        name="integrated_feature",
    ),
    path("feature/<uuid:project_uuid>/", FeaturesView.as_view(), name="features"),
    path("agents/<uuid:project_uuid>/", AgentsView.as_view(), name="agents"),
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
    path(
        "app_integrated_feature/<uuid:project_uuid>/",
        AppIntegratedFeatureView.as_view(),
        name="app-integrated-features",
    ),
    path(
        "nexus/integrate-agent/",
        NexusAgentIntegrationView.as_view(),
        name="integrate-nexus-agent",
    ),
]
