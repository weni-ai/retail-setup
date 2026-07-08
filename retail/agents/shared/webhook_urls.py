from django.conf import settings

from retail.agents.shared.cache import AgentRole, IntegratedAgentCacheHandler

ROLE_DEDICATED_WEBHOOK_PATHS = {
    AgentRole.ABANDONED_CART: "abandoned-cart-webhook",
    AgentRole.PAYMENT_RECOVERY: "payment-recovery-webhook",
}

ROLES_WITH_DEDICATED_WEBHOOK = frozenset(ROLE_DEDICATED_WEBHOOK_PATHS)


def build_integrated_agent_webhook_url(integrated_agent) -> str:
    """Return the public webhook URL for an integrated agent based on its role."""
    domain_url = settings.DOMAIN.rstrip("/")
    agent_uuid = integrated_agent.uuid
    role = IntegratedAgentCacheHandler.resolve_role(integrated_agent)
    dedicated_path = ROLE_DEDICATED_WEBHOOK_PATHS.get(role)

    if dedicated_path:
        return f"{domain_url}/api/v3/agents/{dedicated_path}/{agent_uuid}/"

    return f"{domain_url}/api/v3/agents/webhook/{agent_uuid}/"
