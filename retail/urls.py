from django.contrib import admin
from django.urls import path, include
from django.views.static import serve
from django.conf import settings
from django.urls import re_path
from django.shortcuts import redirect

from retail.healthcheck import views
from retail.api import routers as feature_routers
from retail.webhooks import urls as webhooks_urls
from retail.projects import urls as project_urls
from retail.vtex import urls as vtex_urls
from retail.templates import urls as templates_urls

v3_urls = templates_urls

urlpatterns = [
    path("", lambda _: redirect("admin/", permanent=True)),
    path("admin/", admin.site.urls),
    path("healthcheck/", views.healthcheck, name="healthcheck"),
    path("api/", include(project_urls)),
    path("v2/", include(feature_routers)),
    path("", include(webhooks_urls)),
    path("api/v3/", include(v3_urls)),
    path("vtex/", include(vtex_urls)),
]

urlpatterns.append(
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT})
)
