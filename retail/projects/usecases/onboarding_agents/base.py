from abc import ABC, abstractmethod
from dataclasses import dataclass

from retail.services.nexus.service import NexusService


@dataclass
class AgentContext:
    """Shared context passed to every agent during integration."""

    project_uuid: str
    vtex_account: str


class OnboardingAgent(ABC):
    """
    Base class for agents that must be integrated during onboarding.

    Each concrete agent declares its own UUID, name, and integration
    logic following the rule_mappings pattern: a registry maps channel
    codes to lists of agent instances, and each agent knows how to
    integrate itself.
    """

    uuid: str
    name: str

    @abstractmethod
    def integrate(self, context: AgentContext, nexus_service: NexusService) -> dict:
        pass


class PassiveAgent(OnboardingAgent):
    """Integrated via Nexus app-assign endpoint (simple toggle)."""

    def integrate(self, context: AgentContext, nexus_service: NexusService) -> dict:
        return nexus_service.integrate_agent(context.project_uuid, self.uuid)


class ActiveAgent(OnboardingAgent):
    """
    Integrated via Retail assign endpoint with templates/credentials.

    Structure ready for future use; no concrete active agents exist yet.
    Subclasses must override ``integrate`` with the specific payload.
    """

    templates: list = []

    def integrate(self, context: AgentContext, nexus_service: NexusService) -> dict:
        raise NotImplementedError(
            f"Active agent integration not implemented for {self.name}"
        )
