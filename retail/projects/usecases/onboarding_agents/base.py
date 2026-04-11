from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from retail.services.nexus.service import NexusService


@dataclass
class AgentContext:
    """Shared context passed to every agent during integration.

    Core fields are always set. Channel-specific fields (app_uuid,
    channel_uuid) are populated when the channel provides them —
    e.g. wpp-cloud stores these after channel creation.
    """

    project_uuid: str
    vtex_account: str
    app_uuid: Optional[str] = None
    channel_uuid: Optional[str] = None


class OnboardingAgent(ABC):
    """
    Base class for agents that must be integrated during onboarding.

    Each concrete agent declares its own UUID, name, and integration
    logic following the rule_mappings pattern: a registry maps channel
    codes to lists of agent instances, and each agent knows how to
    integrate itself.
    """

    uuid: str = ""
    name: str

    def _validate_uuid(self) -> None:
        if not self.uuid:
            raise ValueError(
                f"Agent '{self.name}' ({self.__class__.__name__}) has no UUID "
                f"configured."
            )

    @abstractmethod
    def integrate(self, context: AgentContext, nexus_service: NexusService) -> dict:
        pass


class PassiveAgent(OnboardingAgent):
    """Integrated via Nexus app-assign endpoint (simple toggle).

    Instantiated directly with a UUID loaded from environment variables.
    """

    name = "Passive Agent"

    def __init__(self, uuid: str = "", name: str = ""):
        if uuid:
            self.uuid = uuid
        if name:
            self.name = name

    def integrate(self, context: AgentContext, nexus_service: NexusService) -> dict:
        self._validate_uuid()
        return nexus_service.integrate_agent(context.project_uuid, self.uuid)


class ActiveAgent(OnboardingAgent):
    """
    Integrated via AssignAgentUseCase with templates and credentials.

    Requires app_uuid and channel_uuid in the AgentContext.
    Subclasses must override ``integrate`` with the specific payload.
    """

    def _validate_channel_context(self, context: AgentContext) -> None:
        if not context.app_uuid or not context.channel_uuid:
            raise ValueError(
                f"Active agent '{self.name}' requires app_uuid and channel_uuid "
                f"in the context. Ensure the channel was created before "
                f"agent integration."
            )

    @abstractmethod
    def integrate(self, context: AgentContext, nexus_service: NexusService) -> dict:
        pass
