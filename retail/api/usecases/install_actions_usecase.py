from retail.api.tasks import check_templates_synchronization
from retail.clients.exceptions import CustomAPIException
from retail.features.models import Feature, IntegratedFeature
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
        integrated_feature: IntegratedFeature,
        feature: Feature,
        data: dict,
    ):
        actions = feature.config.get("vtex_config", {}).get("install_actions", [])
        wpp_cloud_app_uuid = data["wpp_cloud_app_uuid"]
        flows_channel_uuid = data["flows_channel_uuid"]
        project_uuid = data["project_uuid"]

        if "create_abandoned_cart_template" in actions:
            domain = integrated_feature.project.vtex_account
            domain += ".vtexcommercestable.com.br"
            self._create_abandoned_cart_template(
                integrated_feature=integrated_feature,
                project_uuid=project_uuid,
                wpp_cloud_app_uuid=wpp_cloud_app_uuid,
                domain=domain,
            )

        if "create_order_status_templates" in actions:
            store = data["store"]
            self._create_order_status_templates(
                integrated_feature=integrated_feature,
                project_uuid=project_uuid,
                wpp_cloud_app_uuid=wpp_cloud_app_uuid,
                store=store,
            )

        if "store_flows_channel" in actions:
            self._store_channel(
                integrated_feature=integrated_feature,
                flows_channel_uuid=flows_channel_uuid,
                wpp_cloud_app_uuid=wpp_cloud_app_uuid,
            )

    def _create_abandoned_cart_template(
        self,
        integrated_feature: IntegratedFeature,
        project_uuid: str,
        wpp_cloud_app_uuid: str,
        domain: str,
    ):
        """
        Creates an abandoned cart template and stores the template UUID in the config.
        """
        try:
            # Set initial synchronization status as "pending" before creating templates
            integrated_feature.config["templates_synchronization_status"] = "pending"
            integrated_feature.save(update_fields=["config"])

            # Call the service to create the abandoned cart template
            template = self.integrations_service.create_abandoned_cart_template(
                app_uuid=wpp_cloud_app_uuid, project_uuid=project_uuid, domain=domain
            )
            # Save the template name in the integrated feature config
            integrated_feature.config["abandoned_cart_template"] = template
            integrated_feature.save(update_fields=["config"])

            # Start the task to check template synchronization
            self._check_templates_synchronization(integrated_feature)
        except CustomAPIException as e:
            print(f"Error creating template: {str(e)}")
            raise

    def _store_channel(
        self,
        integrated_feature: IntegratedFeature,
        flows_channel_uuid: str,
        wpp_cloud_app_uuid: str,
    ):
        """
        Fetches the flow channel UUID and stores it in the integrated feature config.
        """
        integrated_feature.config["flow_channel_uuid"] = flows_channel_uuid
        integrated_feature.config["wpp_cloud_app_uuid"] = wpp_cloud_app_uuid
        integrated_feature.save(update_fields=["config"])

    def _create_order_status_templates(
        self,
        integrated_feature: IntegratedFeature,
        project_uuid: str,
        wpp_cloud_app_uuid: str,
        store: str,
    ):
        """
        Creates order status templates using Meta's Template Library and stores
        the generated template names in the integrated feature's config.

        Args:
            integrated_feature (IntegratedFeature): The integrated feature instance to update.
            project_uuid (str): The project UUID for integration.
            wpp_cloud_app_uuid (str): The app UUID for Meta's API.
            store (str): The base URL for the store.

        Raises:
            CustomAPIException: If there is an error during the creation of templates.
        """
        try:
            # Set initial synchronization status as "pending" before creating templates
            integrated_feature.config["templates_synchronization_status"] = "pending"
            integrated_feature.save(update_fields=["config"])

            # Call the service to create the order status templates
            templates = self.integrations_service.create_order_status_templates(
                app_uuid=wpp_cloud_app_uuid, project_uuid=project_uuid, store=store
            )

            # Store the template names in the integrated feature's config
            integrated_feature.config["order_status_templates"] = templates
            integrated_feature.save(update_fields=["config"])

        except Exception as e:
            print(f"Error on process order status templates: {str(e)}")
            raise

    def _check_templates_synchronization(self, integrated_feature: IntegratedFeature):
        """
        Creates a task to check template synchronization status with Meta.

        Args:
            integrated_feature (IntegratedFeature): The integrated feature instance to update.
        """
        try:
            # Call the task to check template synchronization
            check_templates_synchronization.apply_async(
                args=[str(integrated_feature.uuid)], countdown=60  # 1 minute
            )

        except Exception as e:
            print(f"Error scheduling template synchronization check: {str(e)}")
            raise
