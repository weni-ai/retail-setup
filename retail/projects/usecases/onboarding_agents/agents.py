"""
Hard-coded onboarding agents.

Each class represents a Nexus agent that must be integrated
during the onboarding flow. UUIDs are resolved automatically
from ONBOARDING_AGENT_UUIDS using the class name as key.
"""

from retail.projects.usecases.onboarding_agents.base import PassiveAgent


class OrdersAgentCommerceIO(PassiveAgent):
    name = "Orders Agent Commerce IO"


class FeedbackRecorder(PassiveAgent):
    name = "Feedback Recorder 2.0"


class ProductConcierge(PassiveAgent):
    name = "Product Concierge"


class PaymentAgent(PassiveAgent):
    name = "Payment Agent (without catalog)"
