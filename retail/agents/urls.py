from django.urls import path

from retail.agents.views import PushAgentView

urlpatterns = [
    path("push/", PushAgentView.as_view()),
]
