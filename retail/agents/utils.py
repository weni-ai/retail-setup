import logging

from typing import Any, Dict, Optional

from retail.templates.models import Template
from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.services.aws_s3.service import S3Service
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO

logger = logging.getLogger(__name__)


def build_broadcast_template_message(
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
        template_name (str): The name of the template to use.

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
    header = template.metadata.get("header", {})
    s3_key = None
    if header["header_type"] == "IMAGE":
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

    if s3_key is not None:
        message["msg"]["attachment"] = [
            f"img/jpeg:{s3_service.generate_presigned_url(s3_key)}"
        ]

    return message


def adapt_order_status_to_webhook_payload(
    order_status_dto: OrderStatusDTO,
) -> Dict[str, Any]:
    """
    Adapts an OrderStatusDTO instance to a webhook payload format.

    Args:
        order_status_dto (OrderStatusDTO): The DTO with order status information.

    Returns:
        Dict[str, Any]: A dictionary formatted as a webhook payload.
    """
    return {
        "Domain": order_status_dto.domain,
        "OrderId": order_status_dto.orderId,
        "State": order_status_dto.currentState,
        "LastState": order_status_dto.lastState,
        "Origin": {
            "Account": order_status_dto.vtexAccount,
            "Sender": "Gallery",
        },
    }
