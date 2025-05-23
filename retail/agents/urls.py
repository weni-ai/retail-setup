from django.urls import path

from rest_framework.routers import SimpleRouter

from retail.agents.views import (
    PushAgentView,
    AgentViewSet,
    AssignAgentView,
    UnassignAgentView,
    AgentWebhookView,
    IntegratedAgentViewSet,
)

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
