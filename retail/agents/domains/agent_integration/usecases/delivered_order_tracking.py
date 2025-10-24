import logging
from typing import Dict, Any
from uuid import UUID

from django.db import transaction
from django.conf import settings
from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.vtex.usecases.proxy_vtex import ProxyVtexUsecase
from retail.services.vtex_io.service import VtexIOService
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO

logger = logging.getLogger(__name__)


class DeliveredOrderTrackingConfigUseCase:
    """Use case for managing delivered order tracking configuration."""

    def get_integrated_agent(self, pk: UUID) -> IntegratedAgent:
        """Get integrated agent by UUID."""
        try:
            return IntegratedAgent.objects.get(uuid=pk)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found: {pk}")

    def _build_vtex_url(self, integrated_agent: IntegratedAgent) -> str:
        """
        Build VTEX URL using project.vtex_account.

        Args:
            integrated_agent: The integrated agent instance

        Returns:
            VTEX URL string
        """
        vtex_account = integrated_agent.project.vtex_account
        return f"https://{vtex_account}.myvtex.com"

    def _build_webhook_url(self, integrated_agent: IntegratedAgent) -> str:
        """
        Build webhook URL for the integrated agent.

        Args:
            integrated_agent: The integrated agent instance

        Returns:
            Webhook URL string
        """
        domain_url = settings.DOMAIN
        return f"{domain_url}/api/v3/agents/delivered-order-tracking/{str(integrated_agent.uuid)}/"

    def get_tracking_config(self, integrated_agent: IntegratedAgent) -> Dict[str, Any]:
        """
        Get delivered order tracking configuration for an integrated agent.

        Args:
            integrated_agent: The integrated agent instance

        Returns:
            Dict containing delivered order tracking configuration
        """
        tracking_config = integrated_agent.config.get(
            "delivered_order_tracking", {"is_enabled": False}
        )

        return {
            "is_enabled": tracking_config.get("is_enabled", False),
            "webhook_url": tracking_config.get("webhook_url", ""),
        }

    def enable_tracking(
        self, integrated_agent: IntegratedAgent, vtex_app_key: str, vtex_app_token: str
    ) -> Dict[str, Any]:
        """
        Enable delivered order tracking for an integrated agent.

        Args:
            integrated_agent: The integrated agent instance
            vtex_app_key: VTEX application key
            vtex_app_token: VTEX application token

        Returns:
            Dict containing updated tracking configuration

        Raises:
            ValidationError: If credentials are invalid
        """
        # Validate credentials
        if not vtex_app_key or not vtex_app_key.strip():
            raise ValidationError("VTEX app key is required")

        if not vtex_app_token or not vtex_app_token.strip():
            raise ValidationError("VTEX app token is required")

        with transaction.atomic():
            # Get current config or initialize empty dict
            current_config = integrated_agent.config.copy()
            current_tracking_config = current_config.get("delivered_order_tracking", {})

            # Update tracking configuration
            current_tracking_config.update(
                {
                    "is_enabled": True,
                    "vtex_app_key": vtex_app_key.strip(),
                    "vtex_app_token": vtex_app_token.strip(),
                    "vtex_url": self._build_vtex_url(integrated_agent),
                    "webhook_url": self._build_webhook_url(integrated_agent),
                }
            )

            # Update the config
            current_config["delivered_order_tracking"] = current_tracking_config
            integrated_agent.config = current_config
            integrated_agent.save(update_fields=["config"])

            # Create VTEX Hook v3 integration for delivered orders
            self._create_vtex_hook(integrated_agent, current_tracking_config)

            # Update config again with hook_id if created
            current_config["delivered_order_tracking"] = current_tracking_config
            integrated_agent.config = current_config
            integrated_agent.save(update_fields=["config"])

        return self.get_tracking_config(integrated_agent)

    def disable_tracking(self, integrated_agent: IntegratedAgent) -> Dict[str, Any]:
        """
        Disable delivered order tracking for an integrated agent.

        Args:
            integrated_agent: The integrated agent instance

        Returns:
            Dict containing updated tracking configuration
        """
        with transaction.atomic():
            # Get current config or initialize empty dict
            current_config = integrated_agent.config.copy()
            current_tracking_config = current_config.get("delivered_order_tracking", {})

            # Disable tracking
            current_tracking_config["is_enabled"] = False

            # Update the config
            current_config["delivered_order_tracking"] = current_tracking_config
            integrated_agent.config = current_config
            integrated_agent.save(update_fields=["config"])

            # Remove VTEX Hook v3 integration
            self._remove_vtex_hook(integrated_agent, current_tracking_config)

        return self.get_tracking_config(integrated_agent)

    def _create_vtex_hook(
        self, integrated_agent: IntegratedAgent, tracking_config: Dict[str, Any]
    ) -> None:
        """
        Create VTEX Hook v3 for delivered order tracking.

        Args:
            integrated_agent: The integrated agent instance
            tracking_config: Tracking configuration data
        """
        try:
            logger.info(
                f"Creating VTEX Hook for delivered order tracking - agent {integrated_agent.uuid}"
            )

            # Prepare hook data
            hook_data = {
                "filter": {
                    "type": "FromOrders",
                    "expression": '$count(packageAttachment.packages[courierStatus.deliveredDate != "" or courierStatus.finished = true]) > 0',  # noqa: E501
                    "disableSingleFire": False,
                },
                "hook": {"url": tracking_config["webhook_url"]},
            }

            # Prepare headers for VTEX API
            headers = {
                "X-VTEX-API-AppKey": tracking_config["vtex_app_key"],
                "X-VTEX-API-AppToken": tracking_config["vtex_app_token"],
            }

            # Use VTEX proxy to create the hook
            proxy_usecase = ProxyVtexUsecase(vtex_io_service=VtexIOService())
            proxy_usecase.execute(
                method="POST",
                path="/api/orders/hook/config",
                headers=headers,
                data=hook_data,
                project_uuid=str(integrated_agent.project.uuid),
            )

            # VTEX returns empty body on successful hook creation
            # No need to store hook ID since VTEX doesn't provide it and we can't remove specific hooks
            logger.info(
                f"VTEX Hook created successfully for agent {integrated_agent.uuid}"
            )

        except Exception as e:
            logger.exception(
                f"Error creating VTEX Hook for delivered order tracking - agent {integrated_agent.uuid}: {e}"
            )
            raise

    def _remove_vtex_hook(
        self, integrated_agent: IntegratedAgent, tracking_config: Dict[str, Any]
    ) -> None:
        """
        Remove VTEX Hook v3 for delivered order tracking.

        Args:
            integrated_agent: The integrated agent instance
            tracking_config: Tracking configuration data
        """
        try:
            logger.info(
                f"Removing VTEX Hook for delivered order tracking - agent {integrated_agent.uuid}"
            )

            # Prepare headers for VTEX API
            headers = {
                "X-VTEX-API-AppKey": tracking_config["vtex_app_key"],
                "X-VTEX-API-AppToken": tracking_config["vtex_app_token"],
            }

            # Use VTEX proxy to remove the hook
            proxy_usecase = ProxyVtexUsecase(vtex_io_service=VtexIOService())
            proxy_usecase.execute(
                method="DELETE",
                path="/api/orders/hook/config",
                headers=headers,
                project_uuid=str(integrated_agent.project.uuid),
            )

            logger.info(
                f"VTEX Hook removed successfully for agent {integrated_agent.uuid}"
            )

        except Exception as e:
            logger.exception(
                f"Error removing VTEX Hook for delivered order tracking - agent {integrated_agent.uuid}: {e}"
            )
            raise


class DeliveredOrderTrackingWebhookUseCase:
    """Use case for processing delivered order tracking webhook notifications."""

    def get_integrated_agent(self, integrated_agent_uuid: str) -> IntegratedAgent:
        """Get integrated agent by integrated agent UUID."""
        try:
            return IntegratedAgent.objects.get(uuid=integrated_agent_uuid)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found: {integrated_agent_uuid}")

    def validate_tracking_enabled(self, integrated_agent: IntegratedAgent) -> bool:
        """
        Validate if delivered order tracking is enabled for the integrated agent.

        Args:
            integrated_agent: The integrated agent instance

        Returns:
            bool: True if tracking is enabled

        Raises:
            ValidationError: If tracking is not enabled
        """
        tracking_config = integrated_agent.config.get("delivered_order_tracking", {})
        if not tracking_config.get("is_enabled", False):
            raise ValidationError("Delivered order tracking not enabled")
        return True

    def process_webhook_notification(
        self, integrated_agent: IntegratedAgent, webhook_data: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Process delivered order tracking webhook notification.

        Args:
            integrated_agent: The integrated agent instance
            webhook_data: Data received from VTEX webhook

        Returns:
            Dict containing processing result
        """
        try:
            # Validate tracking is enabled
            self.validate_tracking_enabled(integrated_agent)

            # Log the received data
            logger.info(
                f"Received VTEX delivered order tracking webhook for agent {integrated_agent.uuid}: {webhook_data}"
            )

            # Process the notification
            self._process_delivered_order_notification(integrated_agent, webhook_data)

            return {
                "status": "success",
                "message": "Delivered order tracking notification received",
            }

        except ValidationError:
            raise
        except Exception as e:
            logger.exception(
                f"Error processing delivered order tracking notification for agent {integrated_agent.uuid}: {e}"
            )
            raise

    def _process_delivered_order_notification(
        self, integrated_agent: IntegratedAgent, webhook_data: Dict[str, Any]
    ) -> None:
        """
        Process the delivered order tracking notification from VTEX.

        Args:
            integrated_agent: The integrated agent instance
            webhook_data: Data received from VTEX webhook
        """
        try:
            logger.info(
                f"Processing delivered order tracking notification for agent {integrated_agent.uuid}"
            )

            # Get VTEX account from integrated agent's project
            vtex_account = integrated_agent.project.vtex_account

            # Create OrderStatusDTO with "delivered" status
            order_status_dto = OrderStatusDTO(
                recorder=webhook_data.get("Origin", {}),
                domain="OrdersDocumentUpdated",
                orderId=webhook_data.get("OrderId"),
                currentState="delivered",  # Force delivered status
                lastState=webhook_data.get("State"),  # Original state
                vtexAccount=vtex_account,
                lastChangeDate=webhook_data.get("LastChange"),
                currentChangeDate=webhook_data.get("CurrentChange"),
            )

            logger.info(
                f"Created OrderStatusDTO for delivered order: {order_status_dto.orderId} - {order_status_dto}"
            )

            # Use AgentOrderStatusUpdateUsecase to update order status
            order_status_usecase = AgentOrderStatusUpdateUsecase()
            order_status_usecase.execute(integrated_agent, order_status_dto)

            logger.info(
                f"Successfully processed delivered order notification for agent {integrated_agent.uuid}"
            )

        except Exception as e:
            logger.exception(
                f"Error processing delivered order tracking notification: {e}"
            )
            raise
