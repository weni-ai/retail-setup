import logging

from django.conf import settings

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.api.onboard.usecases.dto import ActivateWppCloudDTO

logger = logging.getLogger(__name__)


class ActivateWppCloudUseCase:
    """
    Activates the abandoned cart agent for a WPP Cloud channel
    by setting its contact_percentage.
    """

    def execute(self, dto: ActivateWppCloudDTO) -> IntegratedAgent:
        abandoned_cart_uuid = getattr(settings, "ABANDONED_CART_AGENT_UUID", "")
        if not abandoned_cart_uuid:
            raise ValidationError("ABANDONED_CART_AGENT_UUID is not configured.")

        try:
            integrated_agent = IntegratedAgent.objects.get(
                agent__uuid=abandoned_cart_uuid,
                project__uuid=dto.project_uuid,
                is_active=True,
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(
                f"No active abandoned cart agent found for "
                f"project={dto.project_uuid}"
            )

        integrated_agent.contact_percentage = dto.percentage
        integrated_agent.save(update_fields=["contact_percentage"])

        logger.info(
            f"WPP Cloud abandoned cart activated: "
            f"integrated_agent={integrated_agent.uuid} "
            f"project={dto.project_uuid} "
            f"contact_percentage={dto.percentage}"
        )

        return integrated_agent
