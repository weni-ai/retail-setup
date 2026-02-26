"""
Hard-coded onboarding agents.

Each class represents a Nexus agent that must be integrated
during the onboarding flow. UUIDs match the agent records in Nexus.
"""

from retail.projects.usecases.onboarding_agents.base import PassiveAgent


class OrdersAgentCommerceIO(PassiveAgent):
    uuid = "0270b16a-ae46-4dbc-999f-65699717b0af"
    name = "Orders Agent Commerce IO"


class FeedbackRecorder(PassiveAgent):
    uuid = "5b27dc49-a81d-44a6-a9d8-e882a4f8aada"
    name = "Feedback Recorder 2.0"


class ProductConcierge(PassiveAgent):
    uuid = "d511f81b-1e74-419f-8435-248a0ca7a07a"
    name = "Product Concierge"


class PaymentAgent(PassiveAgent):
    uuid = "69710b8d-db9b-4225-929e-882066d88877"
    name = "Payment Agent (without catalog)"
