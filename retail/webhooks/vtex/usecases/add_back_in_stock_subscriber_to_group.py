import logging
from typing import Optional
from uuid import UUID

from retail.agents.domains.agent_integration.usecases.ensure_back_in_stock_contact_group import (
    BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME,
    EnsureBackInStockContactGroupUseCase,
)
from retail.services.flows.service import (
    FlowsContactUrnAlreadyExistsError,
    FlowsService,
)


logger = logging.getLogger(__name__)


class AddBackInStockSubscriberToGroupUseCase:
    """Put the subscriber in the Flows group without blocking subscribe.

    New contacts are created already in the group. An existing URN gets
    ``contact_actions`` add, which is idempotent. Flows failures are
    logged; the waiter in Retail remains the source of truth for notify.
    """

    def __init__(
        self,
        flows_service: Optional[FlowsService] = None,
        ensure_group: Optional[EnsureBackInStockContactGroupUseCase] = None,
    ) -> None:
        self._flows_service = flows_service or FlowsService()
        self._ensure_group = ensure_group or EnsureBackInStockContactGroupUseCase(
            flows_service=self._flows_service
        )

    def execute(self, project_uuid: UUID, name: str, phone: str) -> None:
        project = str(project_uuid)
        try:
            self._ensure_group.execute(project_uuid)
            self._put_contact_in_group(project, name, phone)
        except Exception as exc:
            logger.exception(
                f"[BACK_IN_STOCK] Failed to add subscriber to Flows group: "
                f"project={project} group={BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME} "
                f"error={exc}"
            )

    def _put_contact_in_group(self, project_uuid: str, name: str, phone: str) -> None:
        urn = f"whatsapp:{phone}"
        try:
            created = self._flows_service.create_contact(
                project_uuid=project_uuid,
                name=name,
                urns=[urn],
                groups=[BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME],
            )
        except FlowsContactUrnAlreadyExistsError:
            self._add_existing_contact_to_group(project_uuid, urn)
            return

        if created is None:
            logger.warning(
                f"[BACK_IN_STOCK] Flows contact was not created: "
                f"project={project_uuid} group={BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME}"
            )
            return

        logger.info(
            f"[BACK_IN_STOCK] Flows contact created in group: "
            f"project={project_uuid} group={BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME}"
        )

    def _add_existing_contact_to_group(self, project_uuid: str, urn: str) -> None:
        added = self._flows_service.add_contact_to_group(
            project_uuid=project_uuid,
            contacts=[urn],
            group=BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME,
        )
        if added is None:
            logger.warning(
                f"[BACK_IN_STOCK] Existing Flows contact was not added to group: "
                f"project={project_uuid} group={BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME}"
            )
            return

        logger.info(
            f"[BACK_IN_STOCK] Existing Flows contact added to group: "
            f"project={project_uuid} group={BACK_IN_STOCK_SUBSCRIBERS_GROUP_NAME}"
        )
