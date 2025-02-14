import locale
import logging

from datetime import datetime

from typing import Optional, Dict

from rest_framework.exceptions import ValidationError

from sentry_sdk import capture_message

from retail.clients.vtex_io.client import VtexIOClient
from retail.features.models import IntegratedFeature
from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.phone_number_normalizer import PhoneNumberNormalizer
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO
from retail.services.flows.service import FlowsService
from retail.clients.flows.client import FlowsClient


logger = logging.getLogger(__name__)


class OrderStatusUseCase:
    """
    Use case for handling order status updates.
    """

    def __init__(
        self,
        data: OrderStatusDTO,
        flows_service: FlowsService = None,
        vtex_io_service: VtexIOService = None,
    ):

        self.flows_service = flows_service or FlowsService(FlowsClient())
        self.vtex_io_service = vtex_io_service or VtexIOService(VtexIOClient())
        self.data = data

    @classmethod
    def _get_domain_by_account(cls, account: str) -> str:
        """
        Get the domain for a given account.
        """
        return f"{account}.myvtex.com"

    def _get_project_by_vtex_account(self) -> Project:
        """
        Get the project by VTEX account.
        """
        project = Project.objects.filter(vtex_account=self.data.vtexAccount).first()

        if not project:
            error_message = f"Project not found for VTEX account {self.data.vtexAccount}. Order id: {self.data.orderId}"
            capture_message(error_message)

            raise ValidationError(
                {"error": "Project not found for this VTEX account"},
                code="project_not_found",
            )

        return project

    def _get_integrated_feature_by_project(self, project: Project) -> IntegratedFeature:
        """
        Get the integrated feature by project.
        """
        integrated_feature = IntegratedFeature.objects.filter(
            project=project,
            feature__code="order_status",
        ).first()

        if not integrated_feature:
            error_message = f"Order status integration not found for project {project.name}. Order id: {self.data.orderId}"
            capture_message(error_message)

            raise ValidationError(
                {"error": "Order status integration not found"},
                code="order_status_integration_not_found",
            )

        return integrated_feature

    def _get_template_by_order_status(
        self, integrated_feature: IntegratedFeature
    ) -> str:
        """
        Get the template for a given order status.
        """
        order_status_templates = integrated_feature.config.get(
            "order_status_templates", {}
        )

        if not order_status_templates:
            error_message = f"Order status templates not found for project {integrated_feature.feature.project.uuid}. Order id: {self.data.orderId}"
            capture_message(error_message)

            raise ValidationError(
                {"error": "Order status templates not found"},
                code="order_status_templates_not_found",
            )

        return order_status_templates.get(self.data.currentState)

    def _get_phone_number_from_order(self, order_data: dict) -> str:
        """
        Get the phone number from the order. Raises an error if the phone number is missing.
        """
        phone_data = order_data.get("clientProfileData", {})
        raw_phone_number = phone_data.get("phone")

        if not raw_phone_number:
            error_message = f"Phone number not found in order {self.data.orderId} - {self.data.vtexAccount}. Cannot proceed."
            logger.error(error_message)
            raise ValidationError(
                {"error": "Phone number is required for message dispatch."},
                code="phone_number_missing",
            )

        return PhoneNumberNormalizer.normalize(raw_phone_number)

    def _get_flow_channel_uuid(self, integrated_feature: str) -> str:
        """
        Get flow_channel_uuid from the integrated feature.
        """
        flow_channel_uuid = integrated_feature.config.get("flow_channel_uuid")
        if not flow_channel_uuid:
            raise ValidationError(
                {"error": "flow_channel_uuid not found"},
                code="flow_channel_uuid_not_found",
            )

        return flow_channel_uuid

    def _get_project_uuid_by_integrated_feature(
        self, integrated_feature: IntegratedFeature
    ) -> str:
        """
        Get the projectUUID for a integrated feature.
        """
        return integrated_feature.project.uuid

    def process_notification(self):
        """
        Process the order status notification.
        """
        project = self._get_project_by_vtex_account()
        account_domain = OrderStatusUseCase._get_domain_by_account(
            self.data.vtexAccount
        )

        integrated_feature = self._get_integrated_feature_by_project(project)
        template_name = self._get_template_by_order_status(integrated_feature)

        order_data = self.vtex_io_service.get_order_details_by_id(
            account_domain=account_domain, order_id=self.data.orderId
        )

        phone_number = self._get_phone_number_from_order(order_data)

        flow_channel_uuid = self._get_flow_channel_uuid(integrated_feature)

        if not self._validate_restrictions(integrated_feature, order_data):
            logger.info(
                f"Skipping notification for order {self.data.orderId} due to active restrictions."
            )
            return  # Interrupts the flow

        message_builder = MessageBuilder(
            phone_number=phone_number,
            template_name=template_name,
            flows_channel_uuid=flow_channel_uuid,
            order_data=order_data,
        )

        message_payload = message_builder.build_message()

        if message_payload:
            self._send_message_to_module(message_payload, integrated_feature)
        else:
            logger.info("No valid message payload found. Skipping message dispatch.")

    def _send_message_to_module(
        self, message_payload: Dict, integrated_feature: IntegratedFeature
    ):
        """
        Send the built message to the flows broadcasts.
        """
        project_uuid = self._get_project_uuid_by_integrated_feature(integrated_feature)
        success = self.flows_service.send_whatsapp_broadcast(
            payload=message_payload, project_uuid=str(project_uuid)
        )
        if success:
            logger.info(
                f"Successfully sent message to the broadcast module for project {project_uuid}."
            )
        else:
            logger.warning(
                f"Failed to send message to the broadcast module for project {project_uuid}."
            )

    def _validate_restrictions(
        self, integrated_feature: IntegratedFeature, order_data
    ) -> bool:
        """
        Checks if the order meets the restrictions set in the integrated feature.
        If restrictions are active, only allowed phone numbers and sellers can proceed.
        Returns False if the notification should be blocked, otherwise True.
        """
        order_status_restriction = integrated_feature.config.get(
            "order_status_restriction", {}
        )

        if order_status_restriction.get("is_active", False):
            # Phone restriction
            phone_list_restriction = order_status_restriction.get("phone_numbers", [])
            if phone_list_restriction:
                order_phone = self._get_phone_number_from_order(order_data)

                # Normalize all numbers in the restriction list
                normalized_phones = {
                    PhoneNumberNormalizer.normalize(number)
                    for number in phone_list_restriction
                }

                if order_phone not in normalized_phones:
                    logger.info(
                        f"Order {self.data.orderId} blocked due to phone restriction: {order_phone}"
                    )
                    return False

            # Seller restriction
            seller_list_restriction = order_status_restriction.get("sellers", [])
            if seller_list_restriction:
                sellers = order_data.get("sellers", [])
                order_seller_ids = {seller.get("id") for seller in sellers}

                # Allows tracking only if at least one seller of the order is in the list
                if not any(
                    seller in seller_list_restriction for seller in order_seller_ids
                ):
                    logger.info(
                        f"Order {self.data.orderId} blocked due to seller restriction: {order_seller_ids}"
                    )
                    return False

        return True


class MessageBuilder:
    """
    Helper to build message payloads for order status notifications.
    """

    def __init__(
        self,
        phone_number: str,
        template_name: str,
        flows_channel_uuid: str,
        order_data: Dict,
    ):
        self.phone_number = phone_number
        self.flows_channel_uuid = flows_channel_uuid
        self.template_name = template_name
        self.order_data = order_data
        self.order_id = self.order_data.get("orderId", "")

    def build_message(self) -> Optional[Dict]:
        """
        Build the message payload based on the order status template.

        Returns:
            dict: The formatted message payload.
        """
        if self.template_name == "weni_purchase_receipt_1":
            return self._build_purchase_receipt_message()
        elif self.template_name == "weni_purchase_transaction_alert":
            return self._build_purchase_transaction_alert_message()
        elif self.template_name == "weni_order_canceled_3":
            return self._build_order_canceled_message()
        elif self.template_name == "weni_order_management_2":
            return self._build_order_management_message()
        elif self.template_name == "weni_payment_confirmation_2":
            return self._build_payment_confirmation_message()
        return None

    def _build_purchase_receipt_message(self) -> Dict:
        """
        Build message for purchase receipt.

        If invoiceUrl is missing, fallback to purchase_transaction_alert.
        """
        invoice_url = self._get_invoice_url()
        if not invoice_url:
            self.template_name = "weni_purchase_transaction_alert"
            return self._build_purchase_transaction_alert_message()  # Fallback

        return {
            "urns": [f"whatsapp:{self.phone_number}"],
            "channel": self.flows_channel_uuid,
            "msg": {
                "template": {
                    "name": self.template_name,
                    "variables": [
                        f"{self._get_total_price()}",
                        self._get_shipping_address(),
                        "comprovante",
                    ],
                },
                "attachments": [f"application/pdf:{invoice_url}"],
            },
        }

    def _build_purchase_transaction_alert_message(self) -> Dict:
        """
        Build message for purchase transaction alert.
        """
        return {
            "urns": [f"whatsapp:{self.phone_number}"],
            "channel": self.flows_channel_uuid,
            "msg": {
                "template": {
                    "name": self.template_name,
                    "variables": [
                        "Compra",
                        f"{self._get_total_price()}",
                        self._get_store_name(),
                        self._get_order_date(),
                    ],
                }
            },
        }

    def _build_order_canceled_message(self) -> Dict:
        """
        Build message for order canceled.
        """
        return {
            "urns": [f"whatsapp:{self.phone_number}"],
            "channel": self.flows_channel_uuid,
            "msg": {
                "template": {
                    "name": self.template_name,
                    "variables": [f"Nº {self.order_id}"],
                },
                "buttons": [
                    {
                        "sub_type": "url",
                        "parameters": [{"type": "text", "text": self.order_id}],
                    }
                ],
            },
        }

    def _build_order_management_message(self) -> Dict:
        """
        Build message for order management.
        """
        return {
            "urns": [f"whatsapp:{self.phone_number}"],
            "channel": self.flows_channel_uuid,
            "msg": {
                "template": {
                    "name": self.template_name,
                    "variables": [
                        self._get_client_name(),
                        f"Nº {self.order_id}",
                        self._get_order_date(),
                    ],
                },
                "buttons": [
                    {
                        "sub_type": "url",
                        "parameters": [{"type": "text", "text": self.order_id}],
                    }
                ],
            },
        }

    def _build_payment_confirmation_message(self) -> Dict:
        """
        Build message for payment confirmation.
        """
        return {
            "urns": [f"whatsapp:{self.phone_number}"],
            "channel": self.flows_channel_uuid,
            "msg": {
                "template": {
                    "name": self.template_name,
                    "variables": [
                        f"{self._get_total_price()}",
                        self._get_payment_method(),
                    ],
                },
                "buttons": [
                    {
                        "sub_type": "url",
                        "parameters": [{"type": "text", "text": self.order_id}],
                    }
                ],
            },
        }

    def _get_client_name(self) -> str:
        """
        Extracts and formats the client's name from order data.
        """
        first_name = (
            self.order_data.get("clientProfileData", {}).get("firstName", "").strip()
        )
        last_name = (
            self.order_data.get("clientProfileData", {}).get("lastName", "").strip()
        )

        full_name = f"{first_name} {last_name}".strip()

        return full_name.title() if full_name else "-"

    def _get_shipping_address(self) -> str:
        """
        Extracts and formats the shipping address from order data.
        """
        address = self.order_data.get("shippingData", {}).get(
            "selectedAddresses", [{}]
        )[0]

        # Using "or ''" to replace None with empty string
        street = (address.get("street") or "").strip()
        number = (address.get("number") or "").strip()
        neighborhood = (address.get("neighborhood") or "").strip()
        city = (address.get("city") or "").strip()
        state = (address.get("state") or "").strip()
        country = (address.get("country") or "").strip()

        locale_str = self.order_data.get("clientPreferencesData", {}).get(
            "locale", "pt-BR"
        )

        # Building address based on location
        if locale_str == "en-US":
            return f"{street} {number}, {city}, {state}, {country}".strip(", ")
        elif locale_str == "es-ES":
            return (
                f"{street} {number}, {neighborhood}, {city}, {state}, {country}".strip(
                    ", "
                )
            )
        else:  # pt-BR
            return (
                f"{street} {number}, {neighborhood}, {city} - {state}, {country}".strip(
                    ", "
                )
            )

    def _get_invoice_url(self) -> Optional[str]:
        """
        Extracts invoice URL, if available.
        """
        packages = self.order_data.get("packageAttachment", {}).get("packages", [])
        if not packages:
            return None

        # Check if the URL exists and ends with ".pdf"
        invoice_url = packages[0].get("invoiceUrl")
        if not invoice_url or not invoice_url.lower().endswith(".pdf"):
            return None

        return invoice_url

    def _parse_datetime(self, date_str: str) -> Optional[datetime]:
        """
        Parses an ISO 8601 datetime string, ensuring compatibility with Python's datetime module.
        """
        if not date_str:
            logger.warning("Received empty date_str in _parse_datetime.")
            return None

        try:
            if "." in date_str:
                date_part, time_part = date_str.split("T")
                time_part, tz_part = (
                    time_part.split("+") if "+" in time_part else time_part.split("-")
                )
                time_main, microseconds = time_part.split(".")
                truncated_microseconds = microseconds[:6]
                date_str = f"{date_part}T{time_main}.{truncated_microseconds}+{tz_part}"

            return datetime.fromisoformat(date_str)

        except ValueError as e:
            logger.error(f"Error parsing datetime: {date_str} - {str(e)}")
            return None

    def _get_order_date(self) -> str:
        """
        Extracts and formats the order creation date based on the client's locale.
        """
        date_str = self.order_data.get("creationDate", "")
        locale_str = self.order_data.get("clientPreferencesData", {}).get(
            "locale", "pt-BR"
        )

        if not date_str:
            return "-"

        try:
            # Converting a string to a datetime object
            dt = self._parse_datetime(date_str)

            locale_mapping = {
                "pt-BR": "pt_BR.utf8",
                "en-US": "en_US.utf8",
                "es-ES": "es_ES.utf8",
            }

            # Try to set locale based on client preference
            try:
                locale.setlocale(
                    locale.LC_TIME, locale_mapping.get(locale_str, "pt_BR.utf8")
                )
            except locale.Error:
                logger.warning(f"Locale '{locale_str}' not available, using default.")
                pass

            if locale_str == "en-US":
                return dt.strftime("%B %d, %Y")
            elif locale_str == "es-ES":
                return dt.strftime("%d de %B de %Y")
            else:  # pt-BR
                return dt.strftime("%d de %B de %Y").capitalize()

        except ValueError:
            return "-"

    def _get_total_price(self) -> str:
        """
        Extracts and formats the total order price based on the store's currency settings.
        """
        value = self.order_data.get("value", 0) / 100
        store_preferences = self.order_data.get("storePreferencesData", {})

        # Get currency symbol and decimal format
        currency_symbol = store_preferences.get("currencySymbol", "R$")
        decimal_separator = store_preferences.get("currencyFormatInfo", {}).get(
            "CurrencyDecimalSeparator", ","
        )
        group_separator = store_preferences.get("currencyFormatInfo", {}).get(
            "CurrencyGroupSeparator", "."
        )

        # Format the number correctly with correct separators
        formatted_value = (
            f"{value:,.2f}".replace(",", "TEMP")
            .replace(".", decimal_separator)
            .replace("TEMP", group_separator)
        )

        # Define whether the symbol should come before or after the value
        starts_with_symbol = store_preferences.get("currencyFormatInfo", {}).get(
            "StartsWithCurrencySymbol", True
        )

        return (
            f"{currency_symbol} {formatted_value}"
            if starts_with_symbol
            else f"{formatted_value} {currency_symbol}"
        )

    def _get_store_name(self) -> str:
        """
        Extracts store name from order data.
        """
        sellers = self.order_data.get("sellers", [{}])
        return sellers[0].get("name", "-")

    def _get_payment_method(self) -> str:
        """
        Extracts payment method from order data.
        """
        transactions = self.order_data.get("paymentData", {}).get("transactions", [])
        if transactions:
            payments = transactions[0].get("payments", [])
            if payments:
                return payments[0].get("paymentSystemName", "-")
        return "-"
