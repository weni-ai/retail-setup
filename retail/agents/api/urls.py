from django.urls import path

from rest_framework.routers import SimpleRouter

from retail.agents.domains.agent_management.views import AgentViewSet, PushAgentView

from retail.agents.domains.agent_integration.views import (
    AssignAgentView,
    UnassignAgentView,
    IntegratedAgentViewSet,
)
from retail.agents.domains.agent_webhook.views import AgentWebhookView

router = SimpleRouter()
router.register(r"assigneds", IntegratedAgentViewSet, basename="assigned-agents")
router.register(r"", AgentViewSet, basename="agents")

urlpatterns = [
    path("push/", PushAgentView.as_view(), name="push-agent"),
    path("<uuid:agent_uuid>/assign/", AssignAgentView.as_view(), name="assign-agent"),
    path(
        "<uuid:agent_uuid>/unassign/",
        UnassignAgentView.as_view(),
        name="unassign-agent",
    ),
    path(
        "webhook/<uuid:webhook_uuid>/", AgentWebhookView.as_view(), name="agent-webhook"
    ),
]

urlpatterns += router.urls
