from typing import Dict, Any
from uuid import UUID

from django.db import transaction
from django.conf import settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.serializers import (
    DevEnvironmentConfigSerializer,
)


class DevEnvironmentConfigUseCase:
    """Use case for managing development environment configuration."""

    def get_dev_config(self, integrated_agent: IntegratedAgent) -> Dict[str, Any]:
        """
        Get development environment configuration for an integrated agent.

        Args:
            integrated_agent: The integrated agent instance

        Returns:
            Dict containing development environment configuration
        """
        dev_config = integrated_agent.config.get(
            "dev_environment", {"phone_numbers": [], "is_dev_mode": False}
        )

        serializer = DevEnvironmentConfigSerializer(dev_config)
        return serializer.data

    def update_dev_config(
        self, integrated_agent: IntegratedAgent, config_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update development environment configuration for an integrated agent.

        Args:
            integrated_agent: The integrated agent instance
            config_data: Configuration data to update

        Returns:
            Dict containing updated development environment configuration
        """
        serializer = DevEnvironmentConfigSerializer(data=config_data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # Get current config or initialize empty dict
            current_config = integrated_agent.config.copy()
            current_dev_config = current_config.get("dev_environment", {})

            # Update only provided fields
            validated_data = serializer.validated_data
            for key, value in validated_data.items():
                current_dev_config[key] = value

            # Ensure required fields exist
            if "phone_numbers" not in current_dev_config:
                current_dev_config["phone_numbers"] = []
            if "is_dev_mode" not in current_dev_config:
                current_dev_config["is_dev_mode"] = False

            # Update the config
            current_config["dev_environment"] = current_dev_config
            integrated_agent.config = current_config
            integrated_agent.save(update_fields=["config"])

        return self.get_dev_config(integrated_agent)

    def get_integrated_agent(self, agent_uuid: UUID) -> IntegratedAgent:
        """
        Get integrated agent by UUID.

        Args:
            agent_uuid: UUID of the integrated agent

        Returns:
            IntegratedAgent instance

        Raises:
            IntegratedAgent.DoesNotExist: If agent not found
        """
        return IntegratedAgent.objects.get(uuid=agent_uuid)


class DevEnvironmentRunUseCase:
    """Use case for running development environment with webhook and phone numbers."""

    def __init__(self):
        # Import here to avoid circular imports
        from retail.agents.domains.agent_webhook.usecases.webhook import (
            AgentWebhookUseCase,
        )
        from retail.interfaces.clients.aws_lambda.client import RequestData

        self.agent_webhook_use_case = AgentWebhookUseCase()
        self.RequestData = RequestData

    def _build_webhook_url(self, integrated_agent: IntegratedAgent) -> str:
        """
        Build webhook URL for the integrated agent.

        Args:
            integrated_agent: The integrated agent instance

        Returns:
            Webhook URL string
        """
        domain_url = settings.DOMAIN
        return f"{domain_url}/api/v3/agents/webhook/{str(integrated_agent.uuid)}/"

    def run_dev_environment(
        self, integrated_agent: IntegratedAgent, dev_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run development environment by sending messages to configured phone numbers.

        Args:
            integrated_agent: The integrated agent instance
            dev_data: Development data to send

        Returns:
            Dict containing execution results
        """
        dev_config = integrated_agent.config.get("dev_environment", {})

        # Check if dev mode is active
        if not dev_config.get("is_dev_mode", False):
            raise ValueError(
                "Development environment is not active. Set is_dev_mode to true to enable development testing."
            )

        phone_numbers = dev_config.get("phone_numbers", [])

        if not phone_numbers:
            raise ValueError("No phone numbers configured for development environment")

        # Build webhook URL
        webhook_url = self._build_webhook_url(integrated_agent)

        results = []

        for phone_number in phone_numbers:
            try:
                # Create request data for the webhook
                # Use dev_data if provided, otherwise use default dev payload
                payload = (
                    dev_data
                    if dev_data
                    else {"message": "Development message from dev environment"}
                )

                request_data = self.RequestData(
                    params={"phone_number": phone_number}, payload=payload
                )

                # Execute the webhook
                self.agent_webhook_use_case.execute(integrated_agent, request_data)

                results.append(
                    {
                        "phone_number": phone_number,
                        "webhook_url": webhook_url,
                        "status": "success",
                        "message": "Message sent successfully",
                    }
                )

            except Exception as e:
                results.append(
                    {
                        "phone_number": phone_number,
                        "webhook_url": webhook_url,
                        "status": "error",
                        "message": str(e),
                    }
                )

        return {
            "webhook_url": webhook_url,
            "total_phone_numbers": len(phone_numbers),
            "successful_sends": len([r for r in results if r["status"] == "success"]),
            "failed_sends": len([r for r in results if r["status"] == "error"]),
            "results": results,
        }
