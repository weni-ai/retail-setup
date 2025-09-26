import logging

import mimetypes

from typing import Any, Callable, Dict, Optional

from datetime import datetime

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.services.flows.service import FlowsService
from retail.templates.models import Template
from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.services.aws_s3.service import S3Service

from weni_datalake_sdk.clients.client import send_commerce_webhook_data
from weni_datalake_sdk.paths.commerce_webhook import CommerceWebhookPath

logger = logging.getLogger(__name__)


class Broadcast:
    def __init__(
        self, flows_service: Optional[FlowsService] = None, audit_func: Callable = None
    ):
        self.flows_service = flows_service or FlowsService()
        self.audit_func = audit_func or send_commerce_webhook_data

    def build_broadcast_template_message(
        self,
        data: Dict[str, Any],
        channel_uuid: str,
        project_uuid: str,
        template: Template,
        s3_service: Optional[S3ServiceInterface] = None,
    ) -> Dict[str, Any]:
        """
        Builds a WhatsApp broadcast message payload based on a template and variable input.

        This function transforms agent-provided input into the expected format for the
        Flows Broadcast API. It processes template variables (ordered by numeric keys),
        and optionally includes a button with a URL if specified.

        Args:
            data (Dict[str, Any]): The input data from the agent, including:
                - "template_variables" (Dict[str, Any]): A dictionary of template variables,
                  where keys are numeric strings representing their position in the message
                  (e.g., "1", "2", ...). May optionally include a key "button" for URL injection.
                - "contact_urn" (str): The WhatsApp contact identifier.
                - "language" (str, optional): The locale for the template (e.g., "pt-BR").
            channel_uuid (str): The UUID of the WhatsApp channel used to send the message.
            project_uuid (str): The UUID of the project associated with the message.
            template (Template): The template object to use for building the message.
            s3_service (Optional[S3ServiceInterface]): Optional S3 service for handling image attachments.

        Returns:
            Dict[str, Any]: A formatted message dictionary for the Flows Broadcast API.
            Returns an empty dictionary if required fields are missing or invalid.
        """
        s3_service = s3_service or S3Service()
        template_variables = data.get("template_variables", {})
        contact_urn = data.get("contact_urn")
        language = data.get("language", "pt-BR")
        template_name = template.current_version.template_name

        # Extract and remove button if present
        button = template_variables.pop("button", None)

        # Extract image s3 key if present
        header = template.metadata.get("header", None)
        s3_key = None
        if header and header["header_type"] == "IMAGE":
            s3_key = header["text"]

        # Sort template variables by numeric key
        sorted_keys = []
        for key in template_variables:
            try:
                int_key = int(key)
                sorted_keys.append((int_key, key))
            except ValueError:
                logger.warning(f"Ignoring non-numeric template variable key: {key}")
                continue

        # Extract values in sorted order
        variables = [
            template_variables[original_key] for _, original_key in sorted(sorted_keys)
        ]

        # Validate required fields before building the message
        if not template_name or not contact_urn or not variables:
            logger.error(
                f"Incomplete message data. "
                f"Template: {template_name}, URN: {contact_urn}, Variables: {variables}"
            )
            return {}

        message: Dict[str, Any] = {
            "project": project_uuid,
            "urns": [contact_urn],
            "channel": channel_uuid,
            "msg": {
                "template": {
                    "locale": language,
                    "name": template_name,
                    "variables": variables,
                }
            },
        }

        # Optionally add button if provided
        if button:
            message["msg"]["buttons"] = [
                {
                    "sub_type": "url",
                    "parameters": [{"type": "text", "text": button}],
                }
            ]

        if s3_key is not None and s3_key.strip():
            content_type, _ = mimetypes.guess_type(s3_key)

            if content_type and content_type.startswith("image/"):
                image_subtype = content_type.split("/")[-1]
                if image_subtype == "jpg":
                    image_subtype = "jpeg"
            else:
                image_subtype = "jpeg"
                logger.warning(
                    f"Could not detect image type for {s3_key}, using jpeg as fallback"
                )

            message["msg"]["attachments"] = [
                f"image/{image_subtype}:{s3_service.generate_presigned_url(s3_key)}"
            ]

        return message

    def can_send_to_contact(
        self, integrated_agent: IntegratedAgent, data: Dict[str, Any]
    ) -> bool:
        """
        Validates whether a contact is allowed to receive the broadcast based on phone restrictions.

        If the 'order_status_restriction' config is present and active, only contacts explicitly listed
        in 'allowed_phone_numbers' will be allowed. If no restriction config exists or is inactive,
        the broadcast is allowed.

        Args:
            integrated_agent (IntegratedAgent): The agent that may have restrictions configured.
            data (Dict[str, Any]): The payload received from the lambda, expected to contain 'contact_urn'.

        Returns:
            bool: True if the message is allowed to be sent, False if it should be blocked.

        Example of valid config:
        {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": true,
                    "allowed_phone_numbers": [
                        "whatsapp:5584996765245",
                        "whatsapp:558498887766"
                    ]
                }
            }
        }
        """
        contact_urn = data.get("contact_urn")
        if not contact_urn:
            logger.warning(
                f"No 'contact_urn' found in payload {data}. Skipping restriction check."
            )
            return False

        config = integrated_agent.config or {}
        if not config:
            return True

        integration_settings = config.get("integration_settings", {})
        order_status_restriction = integration_settings.get("order_status_restriction")

        if not order_status_restriction or not order_status_restriction.get(
            "is_active", False
        ):
            return True

        allowed_numbers = order_status_restriction.get("allowed_phone_numbers")
        if not allowed_numbers:
            logger.info(
                f"Restriction active, but 'allowed_phone_numbers' is missing or empty "
                f"for agent {integrated_agent.uuid}. Blocking by default."
            )
            return False

        if contact_urn not in allowed_numbers:
            logger.info(
                f"Blocked contact due to restriction: {contact_urn} not in "
                f"allowed_phone_numbers for agent {integrated_agent.uuid}."
            )
            return False

        return True

    def send_message(
        self,
        message: Dict[str, Any],
        integrated_agent: IntegratedAgent,
        lambda_data: Optional[Dict[str, Any]] = None,
    ):
        """Send broadcast message via flows service."""
        project_uuid = str(integrated_agent.project.uuid)
        vtex_account = integrated_agent.project.vtex_account
        template_name = (
            message.get("msg", {}).get("template", {}).get("name", "unknown")
        )

        response = self.flows_service.send_whatsapp_broadcast(message)
        self._register_broadcast_event(message, response, integrated_agent, lambda_data)
        logger.info(
            f"Broadcast message sent. "
            f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
            f"Template: {template_name}, Response: {response}"
        )

    def get_current_template(
        self, integrated_agent: IntegratedAgent, data: Dict[str, Any]
    ) -> Optional[str | bool]:
        """Get current template name from integrated agent templates."""
        template_name = data.get("template")
        project_uuid = str(integrated_agent.project.uuid)
        vtex_account = integrated_agent.project.vtex_account

        try:
            template = integrated_agent.templates.get(
                name=template_name, is_active=True
            )
            if template.current_version is None:
                logger.info(
                    f"Template {template_name} has no current version. "
                    f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
                    f"Data: {data}"
                )
                return False
            return template
        except Template.DoesNotExist:
            logger.warning(
                f"Template {template_name} does not exist in database. "
                f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
                f"Data: {data}"
            )
            return None

    def build_message(
        self, integrated_agent: IntegratedAgent, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build broadcast message from lambda response data."""
        project_uuid = str(integrated_agent.project.uuid)
        vtex_account = integrated_agent.project.vtex_account
        template_name = data.get("template", "unknown")

        logger.info(
            f"Retrieving current template name. "
            f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
            f"Template: {template_name}, Data: {data}"
        )
        template = self.get_current_template(integrated_agent, data)

        if template is False:
            logger.info(
                f"Could not build message because template has no current version. "
                f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
                f"Template: {template_name}, Data: {data}"
            )
            return

        if template is None:
            logger.error(
                f"Template not found. "
                f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
                f"Template: {template_name}, Data: {data}"
            )
            return

        logger.info(
            f"Building broadcast template message. "
            f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
            f"Template: {template_name}, Data: {data}"
        )
        message = self.build_broadcast_template_message(
            data=data,
            channel_uuid=str(integrated_agent.channel_uuid),
            project_uuid=project_uuid,
            template=template,
        )
        logger.info(
            f"Broadcast template message built. "
            f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
            f"Template: {template_name}, Message: {message}"
        )
        return message

    def _register_broadcast_event(
        self,
        message: Dict[str, Any],
        response: Dict[str, Any],
        integrated_agent: IntegratedAgent,
        lambda_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Register broadcast event with structured data according to protobuf schema.

        The method extracts data from lambda_data (preferred) or message, following this priority:
        - status: from lambda_data["status"] (ResponseStatus enum values, default: 0)
        - template: from lambda_data["template"] or message structure
        - template_variables: from lambda_data["template_variables"] or message structure (always list)
        - contact_urn: from lambda_data["contact_urn"] or message structure
        - error: from response["error"] (always list)
        - data: {"event_type": "template_broadcast_sent"} (identifies this as template broadcast event)

        Args:
            message: The broadcast message sent to flows service
            response: The response from flows service
            integrated_agent: The integrated agent instance
            lambda_data: Lambda response data containing status, template, template_variables, contact_urn
        """

        # Extract template name from lambda data or message
        template_name = ""
        if lambda_data and "template" in lambda_data:
            template_name = lambda_data["template"]
        elif message and "msg" in message and "template" in message["msg"]:
            template_name = message["msg"]["template"].get("name")

        # Extract contact_urn from lambda data or message
        contact_urn = ""
        if lambda_data and "contact_urn" in lambda_data:
            contact_urn = lambda_data["contact_urn"]
        elif message and "urns" in message and message["urns"]:
            contact_urn = message["urns"][0]

        # Extract template variables from message (always return dict)
        template_variables = {}
        if message and "msg" in message and "template" in message["msg"]:
            variables = message["msg"]["template"].get("variables", [])
            # Convert list to dict with numeric keys
            template_variables = {str(i): var for i, var in enumerate(variables, 1)}

        # Extract error information if present (always return dict)
        error_data = {}
        if response and "error" in response:
            error = response["error"]
            if isinstance(error, dict):
                error_data = error
            else:
                error_data = {"message": str(error)}

        # Build structured data to protobuf schema
        event_data = {
            "template": template_name,
            "template_variables": template_variables,
            "contact_urn": contact_urn,
            "error": error_data,
            "data": {"event_type": "template_broadcast_sent"},
            "date": datetime.now().isoformat(),
            "project": str(integrated_agent.project.uuid),
            "request": message,
            "response": response,
            "agent": str(integrated_agent.agent.uuid),
        }

        # Only include status if it exists in lambda_data
        if lambda_data and "status" in lambda_data:
            event_data["status"] = lambda_data["status"]

        self.audit_func(CommerceWebhookPath, event_data)
