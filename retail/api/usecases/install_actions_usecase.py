from retail.clients.exceptions import CustomAPIException
from retail.services.integrations.service import IntegrationsService
from retail.clients.integrations.client import IntegrationsClient


class InstallActions:
    """
    Executes predefined actions based on feature configuration during integration.
    """

    def __init__(self, integrations_service=None):
        self.integrations_service = integrations_service or IntegrationsService(
            IntegrationsClient()
        )

    def execute(
        self,
        integrated_feature,
        feature,
        data,
    ):
        actions = feature.config.get("vtex_config", {}).get("install_actions", [])

        wpp_cloud_app_uuid = data["wpp_cloud_app_uuid"]
        flows_channel_uuid = data["flows_channel_uuid"]
        project_uuid = data["project_uuid"]

        if "create_abandoned_cart_template" in actions:
            store = data["store"]
            # TODO: validate store fields
            self._create_abandoned_cart_template(
                integrated_feature=integrated_feature,
                project_uuid=project_uuid,
                store=store,
                wpp_cloud_app_uuid=wpp_cloud_app_uuid,
            )

        if "store_flows_channel" in actions:
            self._store_flow_channel_uuid(integrated_feature, flows_channel_uuid)

    def _create_abandoned_cart_template(
        self, integrated_feature, project_uuid, wpp_cloud_app_uuid, store
    ):
        """
        Creates an abandoned cart template and stores the template UUID in the config.
        """
        try:
            template = self.integrations_service.create_abandoned_cart_template(
                app_uuid=wpp_cloud_app_uuid, project_uuid=project_uuid, store=store
            )

            # Store the template details in the integrated feature config
            template_details = {
                "name": template["template_name"],
                "uuid": template["template_uuid"],
            }
            integrated_feature.config["template"] = template_details
            integrated_feature.save()
        except CustomAPIException as e:
            print(f"Error creating template: {str(e)}")
            raise

    def _store_flow_channel_uuid(self, integrated_feature, flows_channel_uuid):
        """
        Fetches the flow channel UUID and stores it in the integrated feature config.
        """
        # Example UUID for simulation (Replace with actual implementation)
        integrated_feature.config["flow_channel_uuid"] = flows_channel_uuid
        integrated_feature.save()
