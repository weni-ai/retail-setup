import logging
from typing import Optional
from uuid import UUID

from retail.services.flows.service import FlowsService


logger = logging.getLogger(__name__)

BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME = "back-in-stock-subscribers"


class EnsureBackInStockContactGroupUseCase:
    """Ensure the back-in-stock subscribers group exists in Flows."""

    def __init__(self, flows_service: Optional[FlowsService] = None) -> None:
        self._flows_service = flows_service or FlowsService()

    def execute(self, project_uuid: UUID) -> None:
        project = str(project_uuid)
        try:
            self._ensure_group(project)
        except Exception as exc:
            logger.exception(
                f"[BACK_IN_STOCK] Failed to ensure contact group: "
                f"project={project} name={BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME} "
                f"error={exc}"
            )

    def _ensure_group(self, project_uuid: str) -> None:
        groups_payload = self._flows_service.get_contact_groups(
            project_uuid=project_uuid,
            name=BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME,
        )
        if groups_payload is None:
            logger.warning(
                f"[BACK_IN_STOCK] Skipping contact group ensure: "
                f"project={project_uuid} name={BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME} "
                f"reason=list_failed"
            )
            return

        if groups_payload.get("results"):
            logger.info(
                f"[BACK_IN_STOCK] Contact group already exists: "
                f"project={project_uuid} name={BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME}"
            )
            return

        created = self._flows_service.create_contact_group(
            project_uuid=project_uuid,
            name=BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME,
        )
        if created is None:
            logger.warning(
                f"[BACK_IN_STOCK] Contact group was not created: "
                f"project={project_uuid} name={BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME}"
            )
            return

        logger.info(
            f"[BACK_IN_STOCK] Contact group created: "
            f"project={project_uuid} name={BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME}"
        )
