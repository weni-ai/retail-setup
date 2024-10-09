# base_service_view.py
from rest_framework import views

from rest_framework.permissions import IsAuthenticated

from retail.clients.flows.client import FlowsClient
from retail.clients.integrations.client import IntegrationsClient
from retail.services.flows.service import FlowsService
from retail.services.integrations.service import IntegrationsService


class BaseServiceView(views.APIView):
    """
    BaseServiceView is a base class that provides common service and client
    injection logic for views. Other views should inherit from this class to
    reuse the integration and flows service logic.
    """

    permission_classes = [IsAuthenticated]

    integrations_service_class = IntegrationsService
    integrations_client_class = IntegrationsClient
    flows_service_class = FlowsService
    flows_client_class = FlowsClient

    _integrations_service = None
    _flows_service = None

    @property
    def integrations_service(self):
        if not self._integrations_service:
            self._integrations_service = self.integrations_service_class(
                self.integrations_client_class()
            )
        return self._integrations_service

    @property
    def flows_service(self):
        if not self._flows_service:
            self._flows_service = self.flows_service_class(self.flows_client_class())
        return self._flows_service