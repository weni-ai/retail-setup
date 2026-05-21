"""
Channel-to-agent mappings for onboarding.

For each supported channel the onboarding integrates a list of
``OnboardingAgent`` instances. Two sources are combined:

* The env ``PASSIVE_AGENTS_<CHANNEL>`` JSON is the canonical source
  of agent UUIDs (devops-controlled). Keys are agent **codes** in
  snake_case; values are UUIDs.
* ``ACTIVE_AGENT_MAPPINGS`` holds legacy active agents that are NOT
  listed in the env JSON because they use their own dedicated env
  var (e.g. ``AbandonedCartAgent`` reads ``ABANDONED_CART_AGENT_UUID``).

Most env entries are integrated with the default ``PassiveAgent``,
which just does a single Nexus ``app-assign`` POST. When a code is
listed in ``PASSIVE_AGENT_OVERRIDES``, that default class is
overridden by the registered one, which does the same app-assign
plus extra setup (credential injection, template setup, etc.). The
env stays the single source of truth for UUIDs; the code only
overrides the integration behavior. The display name passed to
each instance is derived from the code (snake_case → Title Case)
and is used only for logs.
"""

import logging
from typing import Dict, List, Type

from django.conf import settings

from retail.projects.usecases.onboarding_agents.agents import (
    AbandonedCartAgent,
    OneClickPaymentAgent,
)
from retail.projects.usecases.onboarding_agents.base import (
    OnboardingAgent,
    PassiveAgent,
)

logger = logging.getLogger(__name__)


SUPPORTED_CHANNELS = ["wwc", "wpp-cloud"]

# Channel → name of the Django setting that holds the passive
# agent JSON (``{code: uuid}``) for that channel.
PASSIVE_AGENTS_ENV_BY_CHANNEL = {
    "wwc": "PASSIVE_AGENTS_WWC",
    "wpp-cloud": "PASSIVE_AGENTS_WPP_CLOUD",
}

# Legacy active agents that do not live in the env JSON because
# they read their UUID from a dedicated env var.
ACTIVE_AGENT_MAPPINGS: Dict[str, List[OnboardingAgent]] = {
    "wpp-cloud": [
        AbandonedCartAgent(),
    ],
}

# Overrides for entries in PASSIVE_AGENTS_<CHANNEL>: when a code
# matches, the default PassiveAgent is replaced by the registered
# class (typically an ActiveAgent subclass adding credential or
# template setup on top of the standard app-assign).
# Maps channel_code → {agent_code: AgentClass}.
PASSIVE_AGENT_OVERRIDES: Dict[str, Dict[str, Type[OnboardingAgent]]] = {
    "wpp-cloud": {
        "one_click_payment": OneClickPaymentAgent,
    },
}


def get_channel_agents(channel_code: str) -> List[OnboardingAgent]:
    """
    Returns the list of OnboardingAgent instances for a channel.

    Combines env-driven agents (default ``PassiveAgent``, overridden
    by a registered class when the code is in
    ``PASSIVE_AGENT_OVERRIDES``) with the hardcoded active agents
    from ``ACTIVE_AGENT_MAPPINGS``.

    Raises:
        ValueError: If channel_code is not supported.
    """
    if channel_code not in SUPPORTED_CHANNELS:
        raise ValueError(
            f"Unsupported channel '{channel_code}'. Supported: {SUPPORTED_CHANNELS}"
        )

    uuid_by_code = getattr(settings, PASSIVE_AGENTS_ENV_BY_CHANNEL[channel_code], {})
    overrides = PASSIVE_AGENT_OVERRIDES.get(channel_code, {})

    # Catch typos / partial deploys: an override registered in code
    # but absent from the env would be silently skipped otherwise.
    missing_codes = [code for code in overrides if code not in uuid_by_code]
    if missing_codes:
        logger.warning(
            f"Passive agent overrides registered for channel "
            f"'{channel_code}' but missing from env: {missing_codes}. "
            f"These agents will not be integrated."
        )

    agents: List[OnboardingAgent] = [
        _instantiate_agent(code, uuid, overrides)
        for code, uuid in uuid_by_code.items()
        if uuid
    ]
    # ACTIVE_AGENT_MAPPINGS is appended separately: these agents are
    # not env-driven (they have their own dedicated env vars).
    agents.extend(ACTIVE_AGENT_MAPPINGS.get(channel_code, []))
    return agents


def _instantiate_agent(
    code: str,
    uuid: str,
    overrides: Dict[str, Type[OnboardingAgent]],
) -> OnboardingAgent:
    """Picks the override class for ``code`` or falls back to PassiveAgent."""
    display_name = code.replace("_", " ").title()
    agent_cls = overrides.get(code)
    if agent_cls is None:
        return PassiveAgent(uuid=uuid, name=display_name)

    logger.info(
        f"Overriding default PassiveAgent with {agent_cls.__name__} "
        f"for code='{code}'"
    )
    return agent_cls(uuid=uuid, name=display_name)
