"""Clone a VTEX orderForm for abandoned-cart notifications.

Creates a dedicated cart that only the WhatsApp message link can reach,
so UTMs written by the Lambda cannot be attributed to orders the
notification did not drive.
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from retail.services.vtex_checkout.service import VtexCheckoutService
from retail.vtex.usecases.base import BaseVtexUseCase

logger = logging.getLogger(__name__)

# Keys the IO `/order-form-details` route may strip. When any is missing
# from the abandonment-fetched payload we re-read via Checkout.
_CLONE_SOURCE_KEYS = ("marketingData", "shippingData", "salesChannel")

_CLIENT_PROFILE_FIELDS = (
    "email",
    "firstName",
    "lastName",
    "document",
    "documentType",
    "phone",
    "isCorporate",
    "corporateName",
    "corporateDocument",
    "tradeName",
    "stateInscription",
)

_MARKETING_DATA_FIELDS = (
    "utmSource",
    "utmMedium",
    "utmCampaign",
    "utmiCampaign",
    "utmiPart",
    "utmiPage",
    "coupon",
    "marketingTags",
)

_ADDRESS_FIELDS = (
    "addressType",
    "receiverName",
    "isDisposable",
    "postalCode",
    "city",
    "state",
    "country",
    "street",
    "number",
    "neighborhood",
    "complement",
    "reference",
    "geoCoordinates",
)


@dataclass(frozen=True)
class ClonedOrderFormDTO:
    order_form_id: str
    marketing_data: Optional[Dict[str, Any]]


class CloneOrderFormUseCase(BaseVtexUseCase):
    def __init__(self, checkout_service: Optional[VtexCheckoutService] = None) -> None:
        self.checkout_service = checkout_service or VtexCheckoutService()

    def execute(
        self,
        project_uuid: str,
        vtex_account: str,
        order_form: Dict[str, Any],
    ) -> Optional[ClonedOrderFormDTO]:
        """Clone ``order_form`` into a new VTEX cart.

        Items are mandatory. Attachments (profile, shipping, preferences,
        marketing) are best-effort: a failure logs a warning and the clone
        is still returned so the shopper can re-fill at checkout.

        Returns:
            :class:`ClonedOrderFormDTO` on success, or ``None`` when the
            cart could not be created or had no items to copy.
        """
        _, account_domain = self._get_vtex_context(project_uuid)
        source = self._resolve_source_order_form(
            account_domain=account_domain,
            vtex_account=vtex_account,
            order_form=order_form,
        )

        order_items = self._build_order_items(source.get("items") or [])
        if not order_items:
            logger.warning(
                f"Cannot clone orderForm for vtex_account={vtex_account}: "
                f"source has no items"
            )
            return None

        created = self.checkout_service.create_cart(
            account_domain=account_domain,
            vtex_account=vtex_account,
            sales_channel=source.get("salesChannel"),
        )
        if not created or not created.get("orderFormId"):
            logger.error(
                f"Failed to create empty orderForm for clone "
                f"vtex_account={vtex_account}"
            )
            return None

        new_order_form_id = created["orderFormId"]
        logger.info(
            f"Created clone orderForm={new_order_form_id} for "
            f"vtex_account={vtex_account} items_count={len(order_items)}"
        )

        added = self.checkout_service.add_items(
            account_domain=account_domain,
            vtex_account=vtex_account,
            order_form_id=new_order_form_id,
            order_items=order_items,
        )
        if added is None:
            logger.error(
                f"Failed to add items to clone orderForm={new_order_form_id} "
                f"vtex_account={vtex_account}"
            )
            return None

        self._apply_attachments_best_effort(
            account_domain=account_domain,
            vtex_account=vtex_account,
            order_form_id=new_order_form_id,
            source=source,
            clone_items=added.get("items") or [],
        )

        marketing_data = self._build_marketing_data(source.get("marketingData"))
        return ClonedOrderFormDTO(
            order_form_id=new_order_form_id,
            marketing_data=marketing_data,
        )

    def _resolve_source_order_form(
        self,
        account_domain: str,
        vtex_account: str,
        order_form: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return a source orderForm that includes clone-critical fields.

        The IO ``/order-form-details`` route may omit ``marketingData``,
        ``shippingData`` and ``salesChannel``. When any key is absent,
        re-fetch via Checkout so the clone can replicate them.
        """
        if all(key in order_form for key in _CLONE_SOURCE_KEYS):
            return order_form

        source_id = order_form.get("orderFormId")
        if not source_id:
            logger.warning(
                f"orderForm missing clone-critical keys and has no "
                f"orderFormId to re-fetch; vtex_account={vtex_account}"
            )
            return order_form

        logger.info(
            f"Re-fetching orderForm={source_id} via Checkout for clone "
            f"vtex_account={vtex_account}"
        )
        fetched = self.checkout_service.get_order_form(
            account_domain=account_domain,
            vtex_account=vtex_account,
            order_form_id=source_id,
        )
        if not fetched:
            logger.warning(
                f"Checkout re-fetch failed for orderForm={source_id} "
                f"vtex_account={vtex_account}; cloning with available fields"
            )
            return order_form

        return fetched

    def _build_order_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        order_items: List[Dict[str, Any]] = []
        for item in items:
            if not self._should_copy_item(item):
                continue
            order_items.append(
                {
                    "id": item["id"],
                    "quantity": item.get("quantity", 1),
                    "seller": item.get("seller", "1"),
                }
            )
        return order_items

    def _should_copy_item(self, item: Dict[str, Any]) -> bool:
        if item.get("id") is None:
            return False
        if item.get("isGift"):
            return False
        return item.get("parentItemIndex") is None

    def _apply_attachments_best_effort(
        self,
        account_domain: str,
        vtex_account: str,
        order_form_id: str,
        source: Dict[str, Any],
        clone_items: List[Dict[str, Any]],
    ) -> None:
        profile_payload = self._build_client_profile_payload(
            source.get("clientProfileData")
        )
        if profile_payload:
            result = self.checkout_service.set_client_profile_data(
                account_domain=account_domain,
                vtex_account=vtex_account,
                order_form_id=order_form_id,
                client_profile_data=profile_payload,
            )
            if result is None:
                logger.warning(
                    f"Best-effort clientProfileData failed for clone "
                    f"orderForm={order_form_id} vtex_account={vtex_account}"
                )

        self._apply_shipping_best_effort(
            account_domain=account_domain,
            vtex_account=vtex_account,
            order_form_id=order_form_id,
            source=source,
            clone_items=clone_items,
        )

        preferences_payload = self._build_client_preferences_payload(
            source.get("clientPreferencesData")
        )
        if preferences_payload:
            result = self.checkout_service.set_client_preferences_data(
                account_domain=account_domain,
                vtex_account=vtex_account,
                order_form_id=order_form_id,
                client_preferences_data=preferences_payload,
            )
            if result is None:
                logger.warning(
                    f"Best-effort clientPreferencesData failed for clone "
                    f"orderForm={order_form_id} vtex_account={vtex_account}"
                )

        marketing_payload = self._build_marketing_data(source.get("marketingData"))
        if marketing_payload:
            result = self.checkout_service.set_marketing_data(
                account_domain=account_domain,
                vtex_account=vtex_account,
                order_form_id=order_form_id,
                marketing_data=marketing_payload,
            )
            if result is None:
                logger.warning(
                    f"Best-effort marketingData failed for clone "
                    f"orderForm={order_form_id} vtex_account={vtex_account}"
                )

    def _build_client_profile_payload(
        self, client_profile: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not client_profile:
            return None

        payload = {
            field: client_profile[field]
            for field in _CLIENT_PROFILE_FIELDS
            if field in client_profile and client_profile[field] is not None
        }
        if not client_profile.get("isCorporate"):
            for corporate_field in (
                "corporateName",
                "corporateDocument",
                "tradeName",
                "stateInscription",
            ):
                payload.pop(corporate_field, None)

        return payload or None

    def _apply_shipping_best_effort(
        self,
        account_domain: str,
        vtex_account: str,
        order_form_id: str,
        source: Dict[str, Any],
        clone_items: List[Dict[str, Any]],
    ) -> None:
        """Copy shipping in two steps.

        A new cart often has no ``logisticsInfo`` until an address is set.
        Posting source ``itemIndex`` values (or SLAs) in the same request
        is rejected as "invalid item index", especially for pickup carts.
        """
        shipping_data = source.get("shippingData")
        if not shipping_data:
            return

        selected_addresses = self._sanitize_selected_addresses(
            shipping_data.get("selectedAddresses")
        )
        addressed = None
        if selected_addresses:
            addressed = self.checkout_service.set_shipping_data(
                account_domain=account_domain,
                vtex_account=vtex_account,
                order_form_id=order_form_id,
                shipping_data={
                    "clearAddressIfPostalCodeNotFound": False,
                    "selectedAddresses": selected_addresses,
                },
            )
            if addressed is None:
                logger.warning(
                    f"Best-effort shippingData address failed for clone "
                    f"orderForm={order_form_id} vtex_account={vtex_account}"
                )
                return
            clone_items = addressed.get("items") or clone_items

        logistics_info = self._remap_logistics_info(
            source_items=source.get("items") or [],
            source_logistics=shipping_data.get("logisticsInfo") or [],
            clone_items=clone_items,
        )
        if not logistics_info:
            return

        payload: Dict[str, Any] = {"logisticsInfo": logistics_info}
        if addressed is not None:
            clone_addresses = (addressed.get("shippingData") or {}).get(
                "selectedAddresses"
            )
            if clone_addresses:
                payload["selectedAddresses"] = clone_addresses
            elif selected_addresses:
                payload["selectedAddresses"] = selected_addresses

        result = self.checkout_service.set_shipping_data(
            account_domain=account_domain,
            vtex_account=vtex_account,
            order_form_id=order_form_id,
            shipping_data=payload,
        )
        if result is None:
            logger.warning(
                f"Best-effort shippingData SLA selection failed for clone "
                f"orderForm={order_form_id} vtex_account={vtex_account}"
            )

    def _sanitize_selected_addresses(
        self, addresses: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Dict[str, Any]]]:
        if not addresses:
            return None

        sanitized: List[Dict[str, Any]] = []
        for address in addresses:
            payload = {
                field: address[field]
                for field in _ADDRESS_FIELDS
                if field in address and address[field] is not None
            }
            if payload:
                sanitized.append(payload)
        return sanitized or None

    def _remap_logistics_info(
        self,
        source_items: List[Dict[str, Any]],
        source_logistics: List[Dict[str, Any]],
        clone_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Map source logistics rows onto the clone's actual item indexes.

        Source indexes are invalid when the clone has fewer items (gift
        skipped, SKU unavailable, assembly child not sold separately).
        """
        if not clone_items or not source_logistics:
            return []

        source_key_by_index = {
            index: self._item_key(item) for index, item in enumerate(source_items)
        }
        clone_indexes_by_key: Dict[Tuple[str, str], deque] = defaultdict(deque)
        for index, item in enumerate(clone_items):
            clone_indexes_by_key[self._item_key(item)].append(index)

        remapped: List[Dict[str, Any]] = []
        for entry in source_logistics:
            if "itemIndex" not in entry:
                continue
            key = source_key_by_index.get(entry["itemIndex"])
            if key is None or not clone_indexes_by_key[key]:
                continue
            clone_index = clone_indexes_by_key[key].popleft()
            remapped_entry: Dict[str, Any] = {
                "itemIndex": clone_index,
                "selectedSla": entry.get("selectedSla"),
                "selectedDeliveryChannel": entry.get("selectedDeliveryChannel"),
            }
            if entry.get("pickupPointId"):
                remapped_entry["pickupPointId"] = entry["pickupPointId"]
            remapped.append(remapped_entry)
        return remapped

    def _item_key(self, item: Dict[str, Any]) -> Tuple[str, str]:
        return (str(item.get("id")), str(item.get("seller", "1")))

    def _build_client_preferences_payload(
        self, preferences: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not preferences:
            return None

        payload: Dict[str, Any] = {}
        if "locale" in preferences and preferences["locale"] is not None:
            payload["locale"] = preferences["locale"]
        if (
            "optinNewsLetter" in preferences
            and preferences["optinNewsLetter"] is not None
        ):
            payload["optinNewsLetter"] = preferences["optinNewsLetter"]

        return payload or None

    def _build_marketing_data(
        self, marketing_data: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not marketing_data:
            return None

        payload = {
            field: marketing_data[field]
            for field in _MARKETING_DATA_FIELDS
            if field in marketing_data and marketing_data[field] is not None
        }
        return payload or None
