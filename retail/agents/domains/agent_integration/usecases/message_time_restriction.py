import logging
from typing import Any, Dict, Optional
from uuid import UUID

from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.shared.cache import (
    IntegratedAgentCacheHandler,
    IntegratedAgentCacheHandlerRedis,
)

logger = logging.getLogger(__name__)

MESSAGE_TIME_RESTRICTION_KEY = "message_time_restriction"


def project_message_time_restriction(
    config: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return the public send-time restriction shape from an agent config."""
    restriction = (config or {}).get(MESSAGE_TIME_RESTRICTION_KEY)
    if not restriction:
        return {"is_active": False, "periods": None}

    return {
        "is_active": bool(restriction.get("is_active", False)),
        "periods": restriction.get("periods"),
    }


class MessageTimeRestrictionUseCase:
    """Persist abandoned-cart send-time windows on an integrated agent.

    The stored JSON matches the shape ``CartTimeRestrictionService`` already
    reads at dispatch time: ``config.message_time_restriction`` at the
    agent root (not nested under ``abandoned_cart``).
    """

    def __init__(
        self,
        cache_handler: Optional[IntegratedAgentCacheHandler] = None,
    ) -> None:
        self.cache_handler = cache_handler or IntegratedAgentCacheHandlerRedis()

    def get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        """Retrieve an active integrated agent by UUID.

        Args:
            integrated_agent_uuid: Public UUID of the integrated agent.

        Returns:
            The matching active integrated agent.

        Raises:
            NotFound: If no active integrated agent exists with the given UUID.
        """
        try:
            return IntegratedAgent.objects.select_related("project", "agent").get(
                uuid=integrated_agent_uuid, is_active=True
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found {integrated_agent_uuid}")

    def get_restriction(self, integrated_agent: IntegratedAgent) -> Dict[str, Any]:
        """Return the current send-time restriction, or an inactive empty shape."""
        return project_message_time_restriction(integrated_agent.config)

    def upsert_restriction(
        self,
        integrated_agent: IntegratedAgent,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Replace the send-time restriction with a validated full payload."""
        restriction = {
            "is_active": data["is_active"],
            "periods": {
                "weekdays": dict(data["periods"]["weekdays"]),
                "saturdays": dict(data["periods"]["saturdays"]),
            },
        }
        self._write_config(integrated_agent, restriction)
        logger.info(
            f"Updated message time restriction for agent {integrated_agent.uuid}: "
            f"is_active={restriction['is_active']}"
        )
        return self.get_restriction(integrated_agent)

    def delete_restriction(self, integrated_agent: IntegratedAgent) -> None:
        """Remove the send-time restriction key so dispatch uses the default countdown."""
        config = dict(integrated_agent.config or {})
        if MESSAGE_TIME_RESTRICTION_KEY not in config:
            return

        config.pop(MESSAGE_TIME_RESTRICTION_KEY)
        integrated_agent.config = config
        integrated_agent.save(update_fields=["config"])
        self.cache_handler.invalidate_all_for(integrated_agent)
        logger.info(
            f"Removed message time restriction for agent {integrated_agent.uuid}"
        )

    def _write_config(
        self,
        integrated_agent: IntegratedAgent,
        restriction: Dict[str, Any],
    ) -> None:
        config = dict(integrated_agent.config or {})
        config[MESSAGE_TIME_RESTRICTION_KEY] = restriction
        integrated_agent.config = config
        integrated_agent.save(update_fields=["config"])
        self.cache_handler.invalidate_all_for(integrated_agent)
