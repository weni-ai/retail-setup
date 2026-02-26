"""
Channel-to-agent mappings for onboarding.

Maps each supported channel code to the list of agent instances
that must be integrated when that channel is selected.

Pattern follows rule_mappings.py from weni-integrations-engine:
the registry is consumed by IntegrateAgentsUseCase which iterates
over the agents and calls ``agent.integrate(context, nexus_service)``.
"""

from retail.projects.usecases.onboarding_agents.agents import (
    FeedbackRecorder,
    OrdersAgentCommerceIO,
    PaymentAgent,
    ProductConcierge,
)

CHANNEL_AGENT_MAPPINGS = {
    "wwc": [
        OrdersAgentCommerceIO(),
        FeedbackRecorder(),
        ProductConcierge(),
        PaymentAgent(),
    ],
    "wpp-cloud": [],
}

SUPPORTED_CHANNELS = list(CHANNEL_AGENT_MAPPINGS.keys())


def get_channel_agents(channel_code: str) -> list:
    """
    Returns the list of OnboardingAgent instances for a channel.

    Raises:
        ValueError: If channel_code is not supported.
    """
    if channel_code not in CHANNEL_AGENT_MAPPINGS:
        raise ValueError(
            f"Unsupported channel '{channel_code}'. " f"Supported: {SUPPORTED_CHANNELS}"
        )
    return CHANNEL_AGENT_MAPPINGS[channel_code]
