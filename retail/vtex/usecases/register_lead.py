"""
Registers or updates a sales lead for a VTEX account.

First interaction creates the record; subsequent ones refresh the
timestamp, plan, and metrics data, then trigger a Slack notification.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from retail.projects.models import Project
from retail.vtex.models import Lead
from retail.services.vtex_io.service import VtexIOService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegisterLeadDTO:
    user_email: str
    plan: str
    vtex_account: str
    data: dict = field(default_factory=dict)


class RegisterLeadUseCase:
    """
    Creates or updates a Lead record and returns all data
    needed for downstream Slack notification.
    """

    def __init__(
        self,
        vtex_io_service: Optional[VtexIOService] = None,
    ):
        self.vtex_io_service = vtex_io_service or VtexIOService()

    def execute(self, dto: RegisterLeadDTO) -> Lead:
        project = self._get_project(dto.vtex_account)
        region = self._resolve_region(dto.vtex_account)

        lead, created = Lead.objects.update_or_create(
            vtex_account=dto.vtex_account,
            defaults={
                "user_email": dto.user_email,
                "plan": dto.plan,
                "project": project,
                "region": region,
                "data": dto.data,
            },
        )

        action = "Created" if created else "Updated"
        logger.info(
            f"{action} Lead: vtex_account={dto.vtex_account} "
            f"plan={dto.plan} region={region}"
        )

        return lead

    @staticmethod
    def _get_project(vtex_account: str) -> Project:
        try:
            return Project.objects.get(vtex_account=vtex_account)
        except Project.DoesNotExist:
            raise ValueError(f"Project not found for vtex_account: {vtex_account}")

    def _resolve_region(self, vtex_account: str) -> str:
        """Fetch the full VTEX tenant locale (e.g. 'es-MX', 'pt-BR')."""
        account_domain = f"{vtex_account}.myvtex.com"
        try:
            response = self.vtex_io_service.proxy_vtex(
                account_domain=account_domain,
                vtex_account=vtex_account,
                method="GET",
                path=f"/api/tenant/tenants?q={vtex_account}",
            )
            locale = self._extract_locale(response)
            if locale:
                return locale
        except Exception as e:
            logger.warning(
                f"Failed to fetch tenant locale for "
                f"vtex_account={vtex_account}: {e}"
            )
        return ""

    @staticmethod
    def _extract_locale(response) -> Optional[str]:
        if not response:
            return None
        tenant = response if isinstance(response, dict) else None
        if isinstance(response, list) and response:
            tenant = response[0]
        if not tenant:
            return None
        return tenant.get("defaultLocale", "")
