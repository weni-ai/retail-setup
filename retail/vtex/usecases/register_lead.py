"""
Registers or updates a sales lead for a VTEX account.

First interaction creates the record; subsequent ones refresh the
timestamp, plan, and metrics data, then trigger a Slack notification.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService
from retail.services.vtex_io.tenant_locale_service import VtexTenantLocaleService
from retail.vtex.models import Lead

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
        tenant_locale_service: Optional[VtexTenantLocaleService] = None,
    ):
        self.tenant_locale_service = tenant_locale_service or VtexTenantLocaleService(
            vtex_io_service=vtex_io_service
        )

    def execute(self, dto: RegisterLeadDTO) -> Lead:
        project = self._get_project(dto.vtex_account)
        region = self.tenant_locale_service.fetch_default_locale(dto.vtex_account)

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
