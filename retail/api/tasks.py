import logging

from celery import shared_task

from retail.features.models import IntegratedFeature
from retail.services.integrations.service import IntegrationsService
from retail.clients.integrations.client import IntegrationsClient


logger = logging.getLogger(__name__)

@shared_task
def check_templates_synchronization(integrated_feature_uuid: str):
    """
    Task to check if templates are synchronized with Meta.
    """
    try:
        integrated_feature = IntegratedFeature.objects.get(uuid=integrated_feature_uuid)
        integrations_service = IntegrationsService(IntegrationsClient())

        # Get app_uuid from config
        wpp_cloud_app_uuid = integrated_feature.config.get("wpp_cloud_app_uuid")

        if not wpp_cloud_app_uuid:
            logger.warning(f"Wpp cloud app uuid not found for integrated feature {integrated_feature_uuid}")
            return

        # Collect all template names from config
        template_names = integrated_feature.config.get("order_status_templates", {}).values()
        abandoned_cart_template = integrated_feature.config.get("abandoned_cart_template")
        
        if abandoned_cart_template:
            template_names = list(template_names) + [abandoned_cart_template]

        # Get template synchronization status
        sync_status = integrations_service.get_synchronized_templates(
            app_uuid=wpp_cloud_app_uuid, template_list=template_names
        )

        # Update synchronization status in config
        integrated_feature.config["templates_synchronization_status"] = sync_status
        integrated_feature.save()

        # Reattempt sync if status is "pending"
        if sync_status == "pending":
            check_templates_synchronization.apply_async(
                args=[integrated_feature_uuid], countdown=600  # Reattempt in 10 minutes
            )

        elif sync_status == "rejected":
            logger.warning(f"Templates were rejected for {integrated_feature_uuid}. No further attempts.")

    except Exception as e:
        logger.error(f"Error checking template synchronization: {str(e)}")
        raise
