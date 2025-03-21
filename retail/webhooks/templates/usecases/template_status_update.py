import logging

from typing import Dict

from retail.features.models import IntegratedFeature


logger = logging.getLogger(__name__)


class TemplateStatusUpdateUseCase:
    """
    Processes the template statuses received via webhook and updates
    each IntegratedFeature that shares the same app_uuid.
    """

    def handle(
        self, app_uuid: str, template_statuses: Dict[str, str]
    ) -> Dict[str, any]:
        """
        Updates the synchronization status for each IntegratedFeature that has config__wpp_cloud_app_uuid=app_uuid.

        Returns a dictionary containing updated features info.
        """
        if not app_uuid or not template_statuses:
            raise ValueError("app_uuid or template_statuses missing.")

        integrated_features = IntegratedFeature.objects.filter(
            config__wpp_cloud_app_uuid=app_uuid
        )
        if not integrated_features.exists():
            logger.warning(f"No IntegratedFeature found with app_uuid={app_uuid}")
            return {
                "integrated_features_updated": [],
                "final_details": "No integrated features found.",
            }

        updated_features = []

        for integrated_feature in integrated_features:
            tracked_templates = self._collect_tracked_templates(integrated_feature)
            if not tracked_templates:
                logger.warning(
                    f"No tracked templates found for this IntegratedFeature."
                    f"Skipping synchronization for {integrated_feature.uuid}."
                )
                continue

            final_status = self._compute_final_status(
                tracked_templates, template_statuses
            )

            integrated_feature.config["templates_synchronization_status"] = final_status
            integrated_feature.save()

            logger.info(
                f"IntegratedFeature {integrated_feature.uuid} updated to {final_status} via webhook."
            )
            updated_features.append(
                {"uuid": str(integrated_feature.uuid), "status": final_status}
            )

        return {
            "integrated_features_updated": updated_features,
            "final_details": "Webhook processed successfully.",
        }

    def _collect_tracked_templates(self, integrated_feature) -> list:
        """
        Gathers all template names tracked by this IntegratedFeature.
        """
        config = integrated_feature.config
        templates_dict = config.get("order_status_templates", {})
        templates_list = list(templates_dict.values())

        abandoned_cart_template = config.get("abandoned_cart_template")
        if abandoned_cart_template:
            templates_list.append(abandoned_cart_template)

        return templates_list

    def _compute_final_status(
        self, tracked_templates: list, template_statuses: Dict[str, str]
    ) -> str:
        """
        Determines the final status for this IntegratedFeature based on the relevant templates.
        """

        for template_name in tracked_templates:
            status = template_statuses.get(template_name)

            # If status doesn't exist or is pending
            if not status or status == "PENDING":
                return "pending"

            # If status is rejected or error
            if status in ["REJECTED", "ERROR"]:
                return status.lower()

        # If all templates were checked and none were pending or rejected
        return "synchronized"
