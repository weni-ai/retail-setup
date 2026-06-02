from django.urls import path

from retail.webhooks.templates.views.direct_send_category import (
    DirectSendCategoryWebhook,
)
from retail.webhooks.templates.views.template_status_update import (
    TemplatesStatusWebhook,
)


urlpatterns = [
    path(
        "templates-status/api/notification/",
        TemplatesStatusWebhook.as_view(),
        name="templates-status",
    ),
    path(
        "templates-status/api/category-notification/",
        DirectSendCategoryWebhook.as_view(),
        name="direct-send-category-webhook",
    ),
]
