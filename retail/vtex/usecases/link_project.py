"""
Use case for linking an existing project to a VTEX account.

The vtex_account uniqueness validations live at the root (Connect), so this
use case delegates the linking + Insights migration trigger to Connect and
then mirrors the link locally (Retail Project + onboarding).
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from retail.projects.models import Project
from retail.projects.usecases.link_project_to_onboarding import (
    LinkProjectToOnboardingUseCase,
)
from retail.services.connect.service import ConnectService

logger = logging.getLogger(__name__)


@dataclass
class LinkProjectDTO:
    vtex_account: str
    project_uuid: str


class LinkProjectUseCase:
    """Links a project to a VTEX account across Connect, Retail and Insights.

    Steps:
        1. Delegate to Connect, which validates the vtex_account rules,
           persists the link and triggers the Insights migration.
        2. Mirror the link on the local Retail project and onboarding.
    """

    def __init__(self, connect_service: Optional[ConnectService] = None):
        self.connect_service = connect_service or ConnectService()

    def execute(self, dto: LinkProjectDTO) -> Dict:
        self.connect_service.link_vtex_account(
            project_uuid=dto.project_uuid,
            vtex_account=dto.vtex_account,
        )
        logger.info(
            f"[LinkProject] Connect linked vtex_account={dto.vtex_account} "
            f"project_uuid={dto.project_uuid}"
        )

        self._link_local_project(dto)

        return {"success": True}

    def _link_local_project(self, dto: LinkProjectDTO) -> None:
        try:
            project = Project.objects.get(uuid=dto.project_uuid)
        except Project.DoesNotExist:
            logger.warning(
                f"[LinkProject] Local project not found, skipping local link: "
                f"project_uuid={dto.project_uuid}"
            )
            return

        if project.vtex_account != dto.vtex_account:
            project.vtex_account = dto.vtex_account
            project.save(update_fields=["vtex_account"])
            project.clear_cache()

        LinkProjectToOnboardingUseCase.execute(project)
