from rest_framework.routers import DefaultRouter

from django.urls import path, include

from retail.templates.views import (
    TemplateMetricsView,
    TemplateViewSet,
    TemplateLibraryViewSet,
)

router = DefaultRouter()
router.register(r"library", TemplateLibraryViewSet, basename="template-library")
router.register(r"", TemplateViewSet, basename="template")

urlpatterns = [
    path("template-metrics/", TemplateMetricsView.as_view(), name="template-metrics"),
    path("", include(router.urls)),
]
