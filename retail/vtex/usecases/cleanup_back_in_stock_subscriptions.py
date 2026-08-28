import logging
from typing import Iterable, Optional

from django.conf import settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.shared.cache import AgentRole, ROLE_SETTING_NAMES
from retail.services.vtex_io.service import VtexIOService


logger = logging.getLogger(__name__)


class CleanupBackInStockSubscriptionsUseCase:
    """Ask VTEX IO to delete already-sent back-in-stock subscriptions.

    Only accounts with an active back-in-stock agent are contacted. IO
    only removes rows that were already sent and are at least 15 days
    old. Pending subscriptions are left untouched. Failures on one
    account do not stop the remaining accounts. The IO response is
    logged as-is.
    """

    def __init__(self, vtex_io_service: Optional[VtexIOService] = None) -> None:
        self.vtex_io_service = vtex_io_service or VtexIOService()

    def execute(self) -> None:
        for vtex_account in self._active_vtex_accounts():
            self._cleanup_account(vtex_account)
        logger.info("[BACK_IN_STOCK] Cleanup batch finished")

    def _active_vtex_accounts(self) -> Iterable[str]:
        agent_uuid = getattr(settings, ROLE_SETTING_NAMES[AgentRole.BACK_IN_STOCK], "")
        if not agent_uuid:
            logger.warning(
                "[BACK_IN_STOCK] Cleanup skipped: BACK_IN_STOCK_AGENT_UUID "
                "is not configured"
            )
            return []

        return (
            IntegratedAgent.objects.filter(
                is_active=True,
                agent__uuid=agent_uuid,
            )
            .exclude(project__vtex_account__isnull=True)
            .exclude(project__vtex_account="")
            .values_list("project__vtex_account", flat=True)
            .distinct()
        )

    def _cleanup_account(self, vtex_account: str) -> None:
        logger.info(f"[BACK_IN_STOCK] Cleanup starting: vtex_account={vtex_account}")
        result = self.vtex_io_service.cleanup_availability_notify(
            account_domain=f"{vtex_account}.myvtex.com",
            vtex_account=vtex_account,
        )
        if result is None:
            logger.warning(
                f"[BACK_IN_STOCK] Cleanup skipped: vtex_account={vtex_account}"
            )
            return

        logger.info(
            f"[BACK_IN_STOCK] Cleanup finished: vtex_account={vtex_account} "
            f"response={result}"
        )
