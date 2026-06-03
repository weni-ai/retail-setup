from django.urls import path

from rest_framework.routers import SimpleRouter

from retail.agents.domains.agent_execution.views import (
    AgentLogJsonView,
    AgentLogsExportView,
    AgentLogsView,
)
from retail.agents.domains.agent_management.views import AgentViewSet, PushAgentView

from retail.agents.domains.agent_integration.views import (
    AssignAgentView,
    UnassignAgentView,
    IntegratedAgentViewSet,
    DeliveredOrderTrackingConfigView,
    DeliveredOrderTrackingEnableView,
    DeliveredOrderTrackingDisableView,
    DeliveredOrderTrackingWebhookView,
    PaymentRecoveryWebhookView,
    TemplateLanguagesView,
)
from retail.agents.domains.agent_webhook.views import AgentWebhookView

router = SimpleRouter()
router.register(r"assigneds", IntegratedAgentViewSet, basename="assigned-agents")
router.register(r"", AgentViewSet, basename="agents")

urlpatterns = [
    path("push/", PushAgentView.as_view(), name="push-agent"),
    path(
        "template-languages/",
        TemplateLanguagesView.as_view(),
        name="template-languages",
    ),
    path("<uuid:agent_uuid>/assign/", AssignAgentView.as_view(), name="assign-agent"),
    path(
        "<uuid:agent_uuid>/unassign/",
        UnassignAgentView.as_view(),
        name="unassign-agent",
    ),
    path(
        "webhook/<uuid:webhook_uuid>/", AgentWebhookView.as_view(), name="agent-webhook"
    ),
    # Delivered Order Tracking URLs
    path(
        "assigneds/<uuid:pk>/delivered-order-tracking/config/",
        DeliveredOrderTrackingConfigView.as_view(),
        name="delivered-order-tracking-config",
    ),
    path(
        "assigneds/<uuid:pk>/delivered-order-tracking/enable/",
        DeliveredOrderTrackingEnableView.as_view(),
        name="delivered-order-tracking-enable",
    ),
    path(
        "assigneds/<uuid:pk>/delivered-order-tracking/disable/",
        DeliveredOrderTrackingDisableView.as_view(),
        name="delivered-order-tracking-disable",
    ),
    path(
        "delivered-order-tracking/<uuid:pk>/",
        DeliveredOrderTrackingWebhookView.as_view(),
        name="delivered-order-tracking-webhook",
    ),
    path(
        "payment-recovery-webhook/<uuid:pk>/",
        PaymentRecoveryWebhookView.as_view(),
        name="payment-recovery-webhook",
    ),
    path(
        "assigneds/<uuid:agent_uuid>/logs/",
        AgentLogsView.as_view(),
        name="agent-logs",
    ),
    path(
        "assigneds/<uuid:agent_uuid>/logs/export/",
        AgentLogsExportView.as_view(),
        name="agent-logs-export",
    ),
    path(
        "assigneds/<uuid:agent_uuid>/logs/<uuid:log_uuid>/json/",
        AgentLogJsonView.as_view(),
        name="agent-log-json",
    ),
]

urlpatterns += router.urls
