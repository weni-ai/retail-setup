from django.urls import path

from retail.webhooks.templates.views.template_status_update import (
    TemplatesStatusWebhook,
)


urlpatterns = [
    path(
        "templates-status/api/notification/",
        TemplatesStatusWebhook.as_view(),
        name="templates-status",
    ),
]
