from django.urls import path

from retail.api.features.views import FeaturesView

from .integrated_feature.views import IntegratedFeatureView


urlpatterns = [
    path(
        "feature/<uuid:feature_uuid>/integrate/",
        IntegratedFeatureView.as_view(),
        name="integrated_feature",
    ),
    path("feature/<uuid:project_uuid>/", FeaturesView.as_view(), name="features"),
]
