import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from django.conf import settings
from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.services.payment_recovery_hook import (
    DEFAULT_SALES_CHANNELS,
    build_payment_recovery_hook_payload,
)
from retail.agents.shared.cache import (
    IntegratedAgentCacheHandler,
    IntegratedAgentCacheHandlerRedis,
)
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.proxy_vtex import ProxyVtexUsecase

logger = logging.getLogger(__name__)


class PaymentRecoveryHookConfigUseCase:
    """Manage VTEX hook filter configuration for payment recovery agents."""

    def __init__(
        self,
        proxy_vtex_usecase: Optional[ProxyVtexUsecase] = None,
        vtex_io_service: Optional[VtexIOService] = None,
        cache_handler: Optional[IntegratedAgentCacheHandler] = None,
    ):
        """Initialize the use case with optional VTEX proxy dependencies."""
        self._proxy_vtex_usecase = proxy_vtex_usecase
        self._vtex_io_service = vtex_io_service or VtexIOService()
        self.cache_handler = cache_handler or IntegratedAgentCacheHandlerRedis()

    def get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        """Retrieve an active integrated agent by UUID."""
        try:
            return IntegratedAgent.objects.select_related("project").get(
                uuid=integrated_agent_uuid,
                is_active=True,
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found: {integrated_agent_uuid}")

    def get_hook_config(self, integrated_agent: IntegratedAgent) -> Dict[str, Any]:
        """Return the current payment recovery hook configuration."""
        payment_recovery = integrated_agent.config.get("payment_recovery", {})
        return {
            "sales_channels": self._resolve_sales_channels(payment_recovery),
            "hook_created": payment_recovery.get("hook_created", False),
        }

    def update_sales_channels(
        self,
        integrated_agent: IntegratedAgent,
        sales_channels: List[str],
    ) -> Dict[str, Any]:
        """Persist sales channels and sync the VTEX hook filter expression."""
        payment_recovery = integrated_agent.config.get("payment_recovery", {})
        if not payment_recovery.get("hook_created", False):
            raise ValidationError("Payment recovery hook is not configured")

        normalized_channels = self._normalize_sales_channels(sales_channels)

        current_config = integrated_agent.config.copy()
        payment_recovery = current_config.get("payment_recovery", {})
        payment_recovery["sales_channels"] = normalized_channels
        current_config["payment_recovery"] = payment_recovery
        integrated_agent.config = current_config

        self._sync_vtex_hook(integrated_agent, normalized_channels)
        integrated_agent.save(update_fields=["config"])
        self.cache_handler.invalidate_all_for(integrated_agent)

        logger.info(
            f"[PaymentRecovery] Hook sales channels updated - "
            f"agent={integrated_agent.uuid} sales_channels={normalized_channels}"
        )
        return self.get_hook_config(integrated_agent)

    def _resolve_sales_channels(self, payment_recovery: Dict[str, Any]) -> List[str]:
        stored_channels = payment_recovery.get("sales_channels")
        if stored_channels is None:
            return list(DEFAULT_SALES_CHANNELS)
        return list(stored_channels)

    def _normalize_sales_channels(self, sales_channels: List[str]) -> List[str]:
        """Normalize channel ids; an empty list means all sales channels."""
        normalized: List[str] = []
        for channel in sales_channels:
            stripped = str(channel).strip()
            if not stripped:
                raise ValidationError(
                    {"sales_channels": "Sales channel values cannot be empty."}
                )
            if stripped not in normalized:
                normalized.append(stripped)
        return normalized

    def _build_webhook_url(self, integrated_agent: IntegratedAgent) -> str:
        payment_recovery = integrated_agent.config.get("payment_recovery", {})
        webhook_url = payment_recovery.get("webhook_url")
        if webhook_url:
            return webhook_url

        domain_url = settings.DOMAIN
        return (
            f"{domain_url}/api/v3/agents/"
            f"payment-recovery-webhook/{integrated_agent.uuid}/"
        )

    def _get_proxy_usecase(self) -> ProxyVtexUsecase:
        if self._proxy_vtex_usecase is None:
            self._proxy_vtex_usecase = ProxyVtexUsecase(
                vtex_io_service=self._vtex_io_service
            )
        return self._proxy_vtex_usecase

    def _sync_vtex_hook(
        self,
        integrated_agent: IntegratedAgent,
        sales_channels: List[str],
    ) -> None:
        webhook_url = self._build_webhook_url(integrated_agent)
        hook_data = build_payment_recovery_hook_payload(webhook_url, sales_channels)

        logger.info(
            f"[PaymentRecovery] Syncing VTEX hook - "
            f"agent={integrated_agent.uuid} expression={hook_data['filter']['expression']}"
        )

        proxy_usecase = self._get_proxy_usecase()
        proxy_usecase.execute(
            method="POST",
            path="/api/orders/hook/config",
            data=hook_data,
            project_uuid=str(integrated_agent.project.uuid),
        )
