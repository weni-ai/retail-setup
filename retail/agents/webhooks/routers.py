from django.urls import path

from retail.agents.webhooks.views import (
    AgentWebhookView,
)


urlpatterns = [
    path(
        "webhook/<uuid:webhook_uuid>/", AgentWebhookView.as_view(), name="agent-webhook"
    ),
]
