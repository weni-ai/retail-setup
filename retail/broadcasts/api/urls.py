from django.urls import path

from retail.broadcasts.api.views import (
    BroadcastAgentDispatchesView,
    BroadcastAgentSummaryView,
    BroadcastProjectDispatchesView,
    BroadcastProjectSummaryView,
)


urlpatterns = [
    path(
        "projects/dispatches/",
        BroadcastProjectDispatchesView.as_view(),
        name="broadcast-project-dispatches",
    ),
    path(
        "projects/summary/",
        BroadcastProjectSummaryView.as_view(),
        name="broadcast-project-summary",
    ),
    path(
        "assigneds/<uuid:agent_uuid>/dispatches/",
        BroadcastAgentDispatchesView.as_view(),
        name="broadcast-agent-dispatches",
    ),
    path(
        "assigneds/<uuid:agent_uuid>/summary/",
        BroadcastAgentSummaryView.as_view(),
        name="broadcast-agent-summary",
    ),
]
