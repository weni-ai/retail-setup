from django.urls import path
from .views import integrate_feature_view, update_feature_view


urlpatterns = [
    path(
        "projects/<uuid:project_uuid>/integrate/<uuid:feature_uuid>/",
        integrate_feature_view,
        name="integrate_feature",
    ),
    path(
        "projects/<uuid:project_uuid>/update/<uuid:integrated_feature_uuid>/",
        update_feature_view,
        name="update_feature",
    ),
]
