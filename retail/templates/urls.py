from rest_framework.routers import DefaultRouter

from django.urls import path, include

from retail.templates.views import TemplateViewSet, TemplateLibraryViewSet

router = DefaultRouter()
router.register(r"library", TemplateLibraryViewSet, basename="template-library")
router.register(r"", TemplateViewSet, basename="template")

urlpatterns = [
    path("", include(router.urls)),
]
