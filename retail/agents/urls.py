from django.urls import path

from rest_framework.routers import SimpleRouter

from retail.agents.views import PushAgentView, AgentViewSet

router = SimpleRouter()
router.register(r"", AgentViewSet, basename="agents")

urlpatterns = [
    path("push/", PushAgentView.as_view(), name="push-agent"),
]

urlpatterns += router.urls
