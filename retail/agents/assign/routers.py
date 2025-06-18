from django.urls import path

from rest_framework.routers import SimpleRouter

from retail.agents.assign.views import (
    AssignAgentView,
    UnassignAgentView,
    IntegratedAgentViewSet,
)

router = SimpleRouter()
router.register(r"assigneds", IntegratedAgentViewSet, basename="assigned-agents")

urlpatterns = [
    path("<uuid:agent_uuid>/assign/", AssignAgentView.as_view(), name="assign-agent"),
    path(
        "<uuid:agent_uuid>/unassign/",
        UnassignAgentView.as_view(),
        name="unassign-agent",
    ),
]

urlpatterns += router.urls
