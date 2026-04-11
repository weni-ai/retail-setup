"""
Channel-to-agent mappings for onboarding.

Maps each supported channel code to the list of agent instances
that must be integrated when that channel is selected.

Passive agents are loaded from environment variables
(PASSIVE_AGENTS_WWC / PASSIVE_AGENTS_WPP_CLOUD) as JSON dicts
mapping agent name to UUID. Only active agents — which require
complex integration logic — are defined as hardcoded classes.

Pattern follows rule_mappings.py from weni-integrations-engine:
the registry is consumed by IntegrateAgentsUseCase which iterates
over the agents and calls ``agent.integrate(context, nexus_service)``.
"""

from typing import Dict, List

from django.conf import settings

from retail.projects.usecases.onboarding_agents.agents import AbandonedCartAgent
from retail.projects.usecases.onboarding_agents.base import (
    OnboardingAgent,
    PassiveAgent,
)

SUPPORTED_CHANNELS = ["wwc", "wpp-cloud"]

ACTIVE_AGENT_MAPPINGS = {
    "wpp-cloud": [
        AbandonedCartAgent(),
    ],
}


def _build_passive_agents(agents_map: Dict[str, str]) -> List[PassiveAgent]:
    """Creates PassiveAgent instances from a name-to-UUID mapping."""
    return [
        PassiveAgent(uuid=uuid, name=name) for name, uuid in agents_map.items() if uuid
    ]


def get_channel_agents(channel_code: str) -> List[OnboardingAgent]:
    """
    Returns the list of OnboardingAgent instances for a channel.

    Combines passive agents (loaded from env vars) with active agents
    (hardcoded) for the given channel.

    Raises:
        ValueError: If channel_code is not supported.
    """
    if channel_code not in SUPPORTED_CHANNELS:
        raise ValueError(
            f"Unsupported channel '{channel_code}'. " f"Supported: {SUPPORTED_CHANNELS}"
        )

    passive_settings = {
        "wwc": "PASSIVE_AGENTS_WWC",
        "wpp-cloud": "PASSIVE_AGENTS_WPP_CLOUD",
    }

    agents_map = getattr(settings, passive_settings[channel_code], {})
    agents: List[OnboardingAgent] = _build_passive_agents(agents_map)
    agents.extend(ACTIVE_AGENT_MAPPINGS.get(channel_code, []))

    return agents
