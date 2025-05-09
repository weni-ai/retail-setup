from rest_framework.routers import DefaultRouter

from django.urls import path, include

from retail.templates.views import TemplateViewSet

router = DefaultRouter()
router.register(r"templates", TemplateViewSet, basename="template")

urlpatterns = [
    path("", include(router.urls)),
]
