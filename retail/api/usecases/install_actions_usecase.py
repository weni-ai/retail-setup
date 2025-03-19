import logging

from retail.api.tasks import check_templates_synchronization
from retail.clients.exceptions import CustomAPIException
from retail.features.models import Feature, IntegratedFeature
from retail.services.integrations.service import IntegrationsService
from retail.clients.integrations.client import IntegrationsClient
from retail.services.code_actions.service import CodeActionsService
from retail.clients.code_actions.client import CodeActionsClient

logger = logging.getLogger(__name__)


class InstallActions:
    """
    Executes predefined actions based on feature configuration during integration.
    """

    def __init__(self, integrations_service=None, code_actions_service=None):
        self.integrations_service = integrations_service or IntegrationsService(
            IntegrationsClient()
        )
        self.code_actions_service = code_actions_service or CodeActionsService(
            CodeActionsClient()
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
            self._register_code_action(integrated_feature, project_uuid)

        if "create_order_status_templates" in actions:
            store = data["store"]
            self._create_order_status_templates(
                integrated_feature=integrated_feature,
                project_uuid=project_uuid,
                wpp_cloud_app_uuid=wpp_cloud_app_uuid,
                store=store,
            )
            self._register_code_action(integrated_feature, project_uuid)

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
            integrated_feature.save()

            # Call the service to create the abandoned cart template
            template = self.integrations_service.create_abandoned_cart_template(
                app_uuid=wpp_cloud_app_uuid, project_uuid=project_uuid, domain=domain
            )
            # Save the template name in the integrated feature config
            integrated_feature.config["abandoned_cart_template"] = template
            integrated_feature.save()

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
        integrated_feature.save()

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
            integrated_feature.save()

            # Call the service to create the order status templates
            templates = self.integrations_service.create_order_status_templates(
                app_uuid=wpp_cloud_app_uuid, project_uuid=project_uuid, store=store
            )

            # Store the template names in the integrated feature's config
            integrated_feature.config["order_status_templates"] = templates
            integrated_feature.save()

            # Start the task to check template synchronization
            self._check_templates_synchronization(integrated_feature)
        except CustomAPIException as e:
            print(f"Error creating order status templates: {str(e)}")
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
                args=[str(integrated_feature.uuid)], countdown=300  # 5 minutes
            )

        except Exception as e:
            print(f"Error scheduling template synchronization check: {str(e)}")
            raise

    def _register_code_action(
        self, integrated_feature: IntegratedFeature, project_uuid: str
    ):
        """
        Registers a code action for the integrated feature.

        Args:
            integrated_feature (IntegratedFeature): The integrated feature instance to update.
            project_uuid (str): The project UUID for integration.

        Returns:
            dict: The registered action response containing name and ID.

        Raises:
            ValueError: If required data is missing.
            Exception: If there is an error during code action registration.
        """
        try:
            action_code = '''
            import requests
            import json

            def Run(engine):
                """
                Code Action to send a WhatsApp Broadcast message.
                """

                # Getting the request body
                try:
                    request_body = engine.body
                    data = json.loads(request_body)
                except Exception as e:
                    engine.log.error(f"Error processing request body: {e}")
                    engine.result.set({"error": "Invalid request body"}, status_code=400, content_type="json")
                    return

                # Extracting required parameters
                payload = data.get("payload")
                token = data.get("token")
                flows_url = data.get("flows_url")

                # Validating required parameters
                if not payload or not token or not flows_url:
                    engine.log.error("Missing required parameters.")
                    engine.result.set({"error": "Missing required parameters"}, status_code=400, content_type="json")
                    return

                # Sending the message via WhatsApp API
                response = send_whatsapp_broadcast(payload, token, flows_url)

                # Returning the result to the engine
                if response.get("status") == 200:
                    engine.result.set(response, status_code=200, content_type="json")
                else:
                    engine.result.set({"error": "Failed to send message", "details": response}, status_code=500, content_type="json")

            def send_whatsapp_broadcast(payload: dict, token: str, flows_url: str) -> dict:
                """
                Sends a WhatsApp message via the internal API.

                Args:
                    payload (dict): Message data.
                    token (str): Authentication token.
                    flows_url (str): Base URL for the Flows API.

                Returns:
                    dict: API response.
                """

                url = f"{flows_url}/api/v2/internals/whatsapp_broadcasts"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }

                try:
                    response = requests.post(url, json=payload, headers=headers)
                    return {
                        "status": response.status_code,
                        "response": response.json() if response.status_code == 200 else None
                    }
                except requests.RequestException as e:
                    return {
                        "status": 500,
                        "error": str(e)
                    }
            '''
            vtex_account = integrated_feature.project.vtex_account
            action_name = f"{vtex_account}_send_whatsapp_broadcast"

            response = self.code_actions_service.register_code_action(
                action_name=action_name,
                action_code=action_code,
                language="python",
                type="endpoint",
                project_uuid=project_uuid,
            )

            if not response:
                raise ValueError("Response from service is empty")

            response_action_id = response.get("id")
            response_action_name = response.get("name")

            if not response_action_id or not response_action_name:
                raise ValueError(
                    "Response from service does not contain ID or action name"
                )

            action_response = {response_action_name: response_action_id}

            # Update the integrated feature config
            integrated_feature.config["code_action_registered"] = action_response
            integrated_feature.save()

            return action_response

        except ValueError as e:
            logger.error(f"Validation error registering code action: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error registering code action: {str(e)}")
            raise
