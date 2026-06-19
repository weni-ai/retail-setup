import logging

import mimetypes
from urllib.parse import urlparse

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from datetime import datetime

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.broadcasts.models import BroadcastMessage
from retail.agents.domains.agent_webhook.services.direct_send_constants import (
    MAX_BODY_LENGTH,
    MAX_BUTTON_LABEL_LENGTH,
    MAX_FOOTER_LENGTH,
    MAX_HEADER_TEXT_LENGTH,
)
from retail.agents.domains.agent_webhook.services.direct_send_payload_builder import (
    build_direct_send_cta_message,
    build_direct_send_footer,
    build_direct_send_header,
    build_direct_send_quick_replies,
    is_valid_direct_send_template_name,
    substitute_template_variables,
)
from retail.broadcasts.usecases.record_broadcast_sent import (
    BroadcastDispatchContext,
    RecordBroadcastSentDTO,
    RecordBroadcastSentUseCase,
)
from retail.clients.exceptions import CustomAPIException
from retail.services.flows.service import FlowsService
from retail.templates.models import Template
from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.services.aws_s3.service import S3Service

from weni_datalake_sdk.clients.client import send_commerce_webhook_data
from weni_datalake_sdk.paths.commerce_webhook import CommerceWebhookPath

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BroadcastDispatchResult:
    """Outcome of a successful broadcast dispatch through Flows.

    Carries both the raw Flows response (used by upstream callers for
    downstream logging and template lookup) and the UUID of the
    BroadcastMessage row that ``RecordBroadcastSentUseCase`` persisted.
    The latter lets ``AgentWebhookUseCase`` thread the UUID into
    ``ExecutionLoggerService.log_broadcast_sent`` so the FK on
    ``AgentExecution.broadcast_message`` is set, enabling the
    agent-logs API to surface the courier-driven lifecycle
    (delivered / read / failed).

    Only emitted on the success path. The failure path (``CustomAPIException``)
    re-raises the original error after recording a FAILED BroadcastMessage
    out-of-band; the FK linkage is intentionally skipped there because the
    AgentExecution already lands at ``status='error'`` via the upstream
    exception handler.
    """

    response: Dict[str, Any]
    broadcast_message_uuid: Optional[UUID]


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
        template_name = template.current_version.template_name
        language = self._resolve_language(data, template)

        # Extract and remove button if present
        button = template_variables.pop("button", None)

        # Extract image URL if present in template variables
        image_url = template_variables.pop("image_url", None)

        # Extract order_details for Meta WhatsApp payment flows
        order_details = template_variables.pop("order_details", None)

        # Extract payment_buttons for PAYMENT_REQUEST template buttons
        payment_buttons = template_variables.pop("payment_buttons", None)

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
        # variables are optional; template_name and contact_urn are mandatory
        if not template_name or not contact_urn:
            logger.error(
                f"Incomplete message data. "
                f"Template: {template_name}, URN: {contact_urn}"
            )
            return {}

        message: Dict[str, Any] = {
            "project": project_uuid,
            "urns": [contact_urn],
            "channel": channel_uuid,
            "msg": {
                "template": {
                    "name": template_name,
                },
            },
        }

        # Only include locale if language is available
        if language:
            message["msg"]["template"]["locale"] = language

        # Only include variables if provided
        if variables:
            message["msg"]["template"]["variables"] = variables

        # Optionally add button if provided
        if button:
            message["msg"]["buttons"] = [
                {
                    "sub_type": "url",
                    "parameters": [{"type": "text", "text": button}],
                }
            ]

        # Process image attachment - prioritize direct URL over S3 key
        attachment = None
        if image_url:
            # Handle direct image URL
            attachment = self._build_image_attachment_from_url(image_url)
        elif s3_key is not None and s3_key.strip():
            # Handle S3 key (existing logic)
            attachment = self._build_image_attachment_from_s3(s3_key, s3_service)

        # Add attachment to message if available
        if attachment:
            message["msg"]["attachments"] = [attachment]

        if order_details:
            self._apply_order_details(order_details, message)

        if payment_buttons:
            self._apply_payment_buttons(payment_buttons, message)

        return message

    def _resolve_language(
        self, data: Dict[str, Any], template: Template
    ) -> Optional[str]:
        """
        Resolve template language with fallback chain.

        Priority:
        1. Lambda payload (data["language"]) - explicit override
        2. Template metadata (template.metadata["language"]) - stored language

        Converts Meta format (es_MX) to Flows API format (es-MX).

        Args:
            data: Lambda payload data.
            template: Template instance with metadata.

        Returns:
            Language code in Flows API format (e.g., "es-MX") or None.
        """
        language = data.get("language")
        if not language and template.metadata:
            meta_language = template.metadata.get("language")
            if meta_language:
                language = meta_language.replace("_", "-")
        return language

    def _apply_order_details(
        self, order_details: Dict[str, Any], message: Dict[str, Any]
    ) -> None:
        """
        Apply order_details to the message payload.

        Sets interaction_type as "order_details" (fixed value required by Meta's
        WhatsApp API for in-chat payment flows) and passes the order_details
        structure through without transformation.

        Args:
            order_details: Order details dict in Meta's expected format.
            message: The broadcast message dict being built (mutated in place).
        """
        message["msg"]["interaction_type"] = "order_details"
        message["msg"]["order_details"] = order_details
        logger.info(
            f"Applied order_details with reference_id="
            f"{order_details.get('reference_id', 'N/A')}"
        )

    def _apply_payment_buttons(
        self, payment_buttons: list, message: Dict[str, Any]
    ) -> None:
        """
        Apply PAYMENT_REQUEST buttons to the message payload.

        Expects the Lambda to provide a list of button dicts, each with:
        - type: payment type (e.g., "pix_dynamic_code", "payment_link", "boleto")
        - text: the payment data (PIX code, URL, or boleto line)

        Transforms into the Flows Broadcast API format with sub_type "payment_request".

        Args:
            payment_buttons: List of payment button dicts from the Lambda.
            message: The broadcast message dict being built (mutated in place).
        """
        buttons = []
        for pb in payment_buttons:
            buttons.append(
                {
                    "sub_type": "payment_request",
                    "parameters": [
                        {
                            "type": pb.get("type"),
                            "text": pb.get("text"),
                        }
                    ],
                }
            )

        if buttons:
            existing_buttons = message["msg"].get("buttons", [])
            existing_buttons.extend(buttons)
            message["msg"]["buttons"] = existing_buttons

        logger.info(
            f"Applied {len(buttons)} payment_request buttons to broadcast message"
        )

    def _build_image_attachment_from_url(self, image_url: str) -> str:
        """
        Build image attachment string from direct URL.

        Args:
            image_url (str): Direct URL to the image (e.g., "https://example.com/image.png").

        Returns:
            str: Formatted attachment string (e.g., "image/png:https://example.com/image.png").
        """
        # Extract file extension from URL using optimized approach
        try:
            # First try simple endswith for common cases (faster)
            url_lower = image_url.lower()
            if url_lower.endswith((".jpg", ".jpeg")):
                return f"image/jpeg:{image_url}"
            elif url_lower.endswith(".png"):
                return f"image/png:{image_url}"
            elif url_lower.endswith(".gif"):
                return f"image/gif:{image_url}"
            elif url_lower.endswith(".webp"):
                return f"image/webp:{image_url}"
            elif url_lower.endswith(".bmp"):
                return f"image/bmp:{image_url}"

            # Fallback to URL parsing for complex URLs or unknown extensions
            parsed_url = urlparse(image_url)
            path = parsed_url.path

            if "." in path:
                extension = path.split(".")[-1].lower()
                # Map common extensions to MIME types
                extension_map = {
                    "jpg": "jpeg",
                    "jpeg": "jpeg",
                    "png": "png",
                    "gif": "gif",
                    "webp": "webp",
                    "bmp": "bmp",
                }
                image_type = extension_map.get(extension, "jpeg")
                return f"image/{image_type}:{image_url}"
            else:
                return f"image/jpeg:{image_url}"  # Default fallback

        except Exception as e:
            logger.warning(f"Error processing image URL {image_url}: {e}")
            return f"image/jpeg:{image_url}"  # Fallback to jpeg

    def _build_image_attachment_from_s3(
        self, s3_key: str, s3_service: S3ServiceInterface
    ) -> str:
        """
        Build image attachment string from S3 key (existing logic).

        Args:
            s3_key (str): S3 key for the image.
            s3_service (S3ServiceInterface): S3 service instance.

        Returns:
            str: Formatted attachment string with presigned URL.
        """
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

        return f"image/{image_subtype}:{s3_service.generate_presigned_url(s3_key)}"

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
        dispatch_context: Optional[BroadcastDispatchContext] = None,
    ) -> BroadcastDispatchResult:
        """Send broadcast message via flows service.

        Returns a ``BroadcastDispatchResult`` carrying both the raw Flows
        response and the UUID of the persisted ``BroadcastMessage`` row
        (``None`` when persistence failed defensively). Raises
        ``CustomAPIException`` when the Flows call itself rejects the
        dispatch; the failure is audited as a FAILED BroadcastMessage
        out-of-band before re-raising.

        ``dispatch_context`` carries the commercial origin (order_form_id /
        order_id) so the persisted BroadcastMessage row can later be
        matched against an ``invoiced`` event for conversion attribution.
        """
        project_uuid = str(integrated_agent.project.uuid)
        vtex_account = integrated_agent.project.vtex_account
        msg_payload = message.get("msg", {})
        template_name = msg_payload.get("direct_send_template_name") or msg_payload.get(
            "template", {}
        ).get("name", "unknown")

        try:
            response = self.flows_service.send_whatsapp_broadcast(message)
        except CustomAPIException as exc:
            # Audit the failure before re-raising the original error.
            self._record_failed_dispatch(
                message=message,
                integrated_agent=integrated_agent,
                lambda_data=lambda_data,
                exc=exc,
                dispatch_context=dispatch_context,
            )
            raise

        self._register_broadcast_event(message, response, integrated_agent, lambda_data)

        # Resolve the template from the Lambda payload so we can store
        # both template_name and template_version in BroadcastMessage.
        resolved_template: Optional[Template] = None
        if lambda_data:
            try:
                resolved_template = self.get_current_template(
                    integrated_agent, lambda_data
                )
            except Exception as exc:
                logger.warning(
                    f"Could not resolve template for BroadcastMessage record: {exc}"
                )

        broadcast_message = self._record_broadcast_message(
            message=message,
            response=response,
            integrated_agent=integrated_agent,
            template=resolved_template,
            dispatch_context=dispatch_context,
        )
        broadcast_message_uuid = (
            broadcast_message.uuid if broadcast_message is not None else None
        )

        logger.info(
            f"Broadcast message sent. "
            f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
            f"Template: {template_name}, Response: {response}"
        )
        return BroadcastDispatchResult(
            response=response or {},
            broadcast_message_uuid=broadcast_message_uuid,
        )

    def _record_broadcast_message(
        self,
        message: Dict[str, Any],
        response: Dict[str, Any],
        integrated_agent: IntegratedAgent,
        template: Optional[Template],
        dispatch_context: Optional[BroadcastDispatchContext] = None,
    ) -> Optional[BroadcastMessage]:
        """Persist a BroadcastMessage row for end-to-end tracking.

        Kept defensive: a failure to persist must not break the user-facing
        broadcast flow, only surface as a logged error so we can diagnose
        and retry later. Returns the persisted ``BroadcastMessage`` row so
        the caller can link it onto the ``AgentExecution`` audit row, or
        ``None`` when either ``RecordBroadcastSentUseCase`` declined to
        persist (already logged) or an unexpected exception was caught.
        """
        try:
            broadcast_id = self._extract_broadcast_id(response)
            contact_urn = self._extract_contact_urn(message)
            channel_uuid = (
                str(integrated_agent.channel_uuid)
                if integrated_agent.channel_uuid
                else None
            )
            flows_template_uuid = self._extract_flows_template_uuid(response)

            return RecordBroadcastSentUseCase().execute(
                RecordBroadcastSentDTO(
                    broadcast_id=broadcast_id,
                    integrated_agent=integrated_agent,
                    template=template,
                    contact_urn=contact_urn,
                    channel_uuid=channel_uuid,
                    flows_template_uuid=flows_template_uuid,
                    flows_response=response or {},
                    dispatch_context=dispatch_context,
                )
            )
        except Exception as exc:
            logger.exception(
                f"Failed to persist BroadcastMessage for agent "
                f"{integrated_agent.uuid}: {exc}"
            )
            return None

    def _record_failed_dispatch(
        self,
        message: Dict[str, Any],
        integrated_agent: IntegratedAgent,
        lambda_data: Optional[Dict[str, Any]],
        exc: CustomAPIException,
        dispatch_context: Optional[BroadcastDispatchContext] = None,
    ) -> None:
        """Persist a FAILED BroadcastMessage when the Flows call raises.

        Defensive by design: persisting must never mask the original
        dispatch error, so any exception while recording is logged and
        swallowed; the caller re-raises ``exc`` after this returns.
        """
        try:
            resolved_template: Optional[Template] = None
            if lambda_data:
                try:
                    resolved_template = self.get_current_template(
                        integrated_agent, lambda_data
                    )
                except Exception:
                    resolved_template = None

            status_code = getattr(exc, "status_code", None)
            error_detail = getattr(exc, "detail", str(exc))
            error_message = (
                f"{type(exc).__name__}(status_code={status_code}): {error_detail}"
            )
            contact_urn = self._extract_contact_urn(message)
            channel_uuid = (
                str(integrated_agent.channel_uuid)
                if integrated_agent.channel_uuid
                else None
            )

            RecordBroadcastSentUseCase().execute(
                RecordBroadcastSentDTO(
                    broadcast_id=None,
                    integrated_agent=integrated_agent,
                    template=resolved_template,
                    contact_urn=contact_urn,
                    channel_uuid=channel_uuid,
                    flows_template_uuid=None,
                    flows_response={
                        "error": str(error_detail),
                        "status_code": status_code,
                    },
                    error_message=error_message,
                    dispatch_context=dispatch_context,
                )
            )
        except Exception as record_exc:
            logger.exception(
                f"Failed to persist FAILED BroadcastMessage for agent "
                f"{integrated_agent.uuid}: {record_exc}"
            )

    @staticmethod
    def _extract_broadcast_id(response: Optional[Dict[str, Any]]) -> Optional[int]:
        """Extract the broadcast id from the Flows response.

        Flows returns the broadcast id under the key ``id`` in the
        top-level of the JSON body. Coerce to int defensively so that
        the consumer side always sees an integer.
        """
        if not response or not isinstance(response, dict):
            return None

        raw_value = response.get("id")
        if raw_value is None:
            return None

        try:
            return int(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                f"Unexpected broadcast id format in Flows response: {raw_value!r}"
            )
            return None

    @staticmethod
    def _extract_flows_template_uuid(
        response: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Extract the template UUID from the Flows response metadata.

        The Flows response carries the template identity in
        ``metadata.template.uuid``; this is the template UUID on the
        Flows side and is distinct from our local ``Template.uuid``.
        """
        if not response or not isinstance(response, dict):
            return None

        metadata = response.get("metadata") or {}
        template = metadata.get("template") or {}
        value = template.get("uuid")
        return value if value else None

    @staticmethod
    def _extract_contact_urn(message: Optional[Dict[str, Any]]) -> str:
        if not message or not isinstance(message, dict):
            return ""
        urns = message.get("urns") or []
        if urns:
            return urns[0]
        return ""

    def get_current_template(
        self, integrated_agent: IntegratedAgent, data: Dict[str, Any]
    ) -> Optional[Template]:
        """Resolve the dispatchable ``Template`` by name, or ``None`` on skip.

        ``APPROVED`` returns the Template; every other outcome (including
        no-row) routes through ``_log_dispatch_skipped_due_to_status``.
        Anchor: FR-012 / FR-039 (see
        ``specs/002-direct-send-broadcasts/spec.md``).
        """
        template_name = data.get("template")
        project_uuid = str(integrated_agent.project.uuid)
        vtex_account = integrated_agent.project.vtex_account

        if not template_name:
            logger.warning(
                f"No template name provided in data. "
                f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
                f"Data: {data}"
            )
            return None

        template = (
            integrated_agent.templates.filter(
                name=template_name,
                is_active=True,
                current_version__isnull=False,
            )
            .select_related("current_version")
            .first()
        )

        status = template.current_version.status if template else "NOT_FOUND"

        if status == "APPROVED":
            return template

        self._log_dispatch_skipped_due_to_status(
            integrated_agent=integrated_agent,
            template_name=template_name,
            version_status=status,
            data=data,
        )
        return None

    @staticmethod
    def _log_dispatch_skipped_due_to_status(
        *,
        integrated_agent: IntegratedAgent,
        template_name: str,
        version_status: str,
        data: Dict[str, Any],
    ) -> None:
        """Emit the unified "Dispatch-gate skip" audit log line.

        Anchor: FR-039 (single shape for every non-``APPROVED`` skip
        class) + FR-027 Exception clause + FR-044 (top-level tenant
        keys).
        """
        logger.warning(
            f"[BroadcastDispatch] skipped_due_to_status: "
            f"project_uuid={integrated_agent.project.uuid} "
            f"vtex_account={integrated_agent.project.vtex_account} "
            f"agent={integrated_agent.uuid} "
            f"template={template_name} "
            f"version_status={version_status} event={data}"
        )

    def build_direct_send_message(
        self,
        data: Dict[str, Any],
        channel_uuid: str,
        project_uuid: str,
        template: Template,
        integrated_agent: IntegratedAgent,
    ) -> Optional[Dict[str, Any]]:
        """Build the Direct Send broadcast payload, or ``None`` on refusal.

        Refusal reasons emit ``skipped_due_to_direct_send_validation``
        WARNING and return ``None``. Anchor: FR-014a / FR-014b / FR-014c
        / FR-014d / FR-017 / FR-039 (see
        ``specs/002-direct-send-broadcasts/spec.md``;
        ``contracts/messaging-gateway-payload.md`` §3).
        """
        template_variables = dict(data.get("template_variables") or {})
        contact_urn = data.get("contact_urn")
        template_name = template.current_version.template_name
        metadata = template.metadata or {}

        image_url = template_variables.pop("image_url", None)
        template_variables.pop("button", None)
        template_variables.pop("order_details", None)
        template_variables.pop("payment_buttons", None)

        if not contact_urn:
            logger.error(
                f"Incomplete Direct Send message data. "
                f"Template: {template_name}, URN: {contact_urn}"
            )
            return None

        if not is_valid_direct_send_template_name(template_name):
            self._log_direct_send_refusal(
                integrated_agent=integrated_agent,
                template_name=template_name,
                reason="naming_rule",
                data=data,
            )
            return None

        body = metadata.get("body")
        if not body:
            self._log_direct_send_refusal(
                integrated_agent=integrated_agent,
                template_name=template_name,
                reason="empty_body",
                data=data,
            )
            return None

        substituted_body = substitute_template_variables(
            body, template_variables, template_name=template_name
        )
        header = build_direct_send_header(
            metadata,
            template_variables,
            template_name=template_name,
            image_url=image_url,
        )
        footer = build_direct_send_footer(
            metadata, template_variables, template_name=template_name
        )
        cta_message = build_direct_send_cta_message(
            metadata, template_variables, template_name=template_name
        )
        quick_replies = build_direct_send_quick_replies(
            metadata, template_variables, template_name=template_name
        )

        if self._exceeds_direct_send_length_limits(
            body=substituted_body,
            header=header,
            footer=footer,
            cta_message=cta_message,
            quick_replies=quick_replies,
        ):
            self._log_direct_send_refusal(
                integrated_agent=integrated_agent,
                template_name=template_name,
                reason="component_length_limit",
                data=data,
            )
            return None

        msg: Dict[str, Any] = {
            "direct_send": True,
            "category": "utility",
            "direct_send_template_name": template_name,
            "text": substituted_body,
        }
        if header is not None:
            msg["header"] = header
        if footer is not None:
            msg["footer"] = footer
        if cta_message is not None:
            msg["interaction_type"] = "cta_url"
            msg["cta_message"] = cta_message
        if quick_replies:
            msg["quick_replies"] = quick_replies
        if header is not None and header.get("type") == "image":
            msg["attachments"] = [f"image/jpeg:{header['image_url']}"]

        return {
            "project": project_uuid,
            "urns": [contact_urn],
            "channel": channel_uuid,
            "msg": msg,
        }

    @staticmethod
    def _exceeds_direct_send_length_limits(
        *,
        body: str,
        header: Optional[Dict[str, Any]],
        footer: Optional[str],
        cta_message: Optional[Dict[str, Any]],
        quick_replies: Optional[List[str]],
    ) -> bool:
        if len(body) > MAX_BODY_LENGTH:
            return True
        if (
            header is not None
            and header.get("type") == "text"
            and len(header.get("text", "")) > MAX_HEADER_TEXT_LENGTH
        ):
            return True
        if footer is not None and len(footer) > MAX_FOOTER_LENGTH:
            return True
        if (
            cta_message is not None
            and len(cta_message.get("display_text", "")) > MAX_BUTTON_LABEL_LENGTH
        ):
            return True
        for title in quick_replies or []:
            if len(title) > MAX_BUTTON_LABEL_LENGTH:
                return True
        return False

    @staticmethod
    def _log_direct_send_refusal(
        *,
        integrated_agent: IntegratedAgent,
        template_name: str,
        reason: str,
        data: Dict[str, Any],
    ) -> None:
        """Emit the Direct Send validation skip audit log line.

        Anchor: FR-039 (refusal shape) + FR-044 (top-level
        ``project_uuid``) + Research Decision 7 (``reason``
        discriminator).
        """
        logger.warning(
            f"[BroadcastDispatch] skipped_due_to_direct_send_validation: "
            f"project_uuid={integrated_agent.project.uuid} "
            f"agent={integrated_agent.uuid} "
            f"template={template_name} "
            f"reason={reason} event={data}"
        )

    def build_message(
        self, integrated_agent: IntegratedAgent, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Build broadcast message from lambda response data.

        Routes between legacy and Direct Send paths based on
        ``IntegratedAgent.config["direct_send"]``. Anchor: FR-001 /
        FR-005 / FR-025 (absence is the canonical legacy marker).
        """
        project_uuid = str(integrated_agent.project.uuid)
        vtex_account = integrated_agent.project.vtex_account
        template_name = data.get("template", "unknown")

        logger.info(
            f"Retrieving current template name. "
            f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
            f"Template: {template_name}, Data: {data}"
        )
        template = self.get_current_template(integrated_agent, data)

        if template is None:
            logger.warning(
                f"Template not found or has no approved current version. "
                f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
                f"Template: {template_name}, Data: {data}"
            )
            return

        logger.info(
            f"Building broadcast template message. "
            f"Project: {project_uuid}, VTEX Account: {vtex_account}, "
            f"Template: {template_name}, Data: {data}"
        )

        if integrated_agent.config.get("direct_send", False):
            message = self.build_direct_send_message(
                data=data,
                channel_uuid=str(integrated_agent.channel_uuid),
                project_uuid=project_uuid,
                template=template,
                integrated_agent=integrated_agent,
            )
        else:
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

        # Extract template name from lambda data or message.
        template_name = ""
        if lambda_data and "template" in lambda_data:
            template_name = lambda_data["template"]
        elif message and "msg" in message:
            msg_payload = message["msg"]
            template_name = msg_payload.get(
                "direct_send_template_name"
            ) or msg_payload.get("template", {}).get("name", "")

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

        if lambda_data and "status" in lambda_data:
            event_data["status"] = lambda_data["status"]

        self.audit_func(CommerceWebhookPath, event_data)
