"""VTEX order total and currency helpers for agent execution logging."""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from retail.interfaces.services.execution_logger import ExecutionLoggerServiceInterface
from retail.services.vtex_io.service import VtexIOService

logger = logging.getLogger(__name__)

_AMOUNT_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class OrderAmountDetails:
    """Order total and store currency resolved from a VTEX order payload."""

    amount: Optional[Decimal]
    currency: Optional[str]


def parse_order_amount_details(
    order_details: Optional[Dict[str, Any]],
) -> OrderAmountDetails:
    """Extract the order total (major units) and currency from VTEX order JSON.

    VTEX returns ``order.value`` in minor units (cents). The amount is
    divided by 100 and quantized to two decimal places.
    """
    if not order_details:
        return OrderAmountDetails(amount=None, currency=None)

    store_preferences = order_details.get("storePreferencesData") or {}
    currency = store_preferences.get("currencyCode") or None

    raw_value = order_details.get("value")
    if raw_value in (None, ""):
        return OrderAmountDetails(amount=None, currency=currency)

    try:
        amount = (Decimal(raw_value) / Decimal(100)).quantize(_AMOUNT_QUANTUM)
    except (TypeError, ValueError, ArithmeticError):
        return OrderAmountDetails(amount=None, currency=currency)

    return OrderAmountDetails(amount=amount, currency=currency)


def apply_order_amount_details(
    exec_logger: ExecutionLoggerServiceInterface,
    details: OrderAmountDetails,
) -> None:
    """Push parsed order totals onto the active execution log when present."""
    if details.amount is not None or details.currency:
        exec_logger.update_order_info(
            amount=details.amount,
            currency=details.currency,
        )


def fetch_order_amount_details(
    vtex_io_service: VtexIOService,
    *,
    order_id: Optional[str],
    vtex_account: str,
    log_prefix: str = "[VTEX_ORDER]",
) -> OrderAmountDetails:
    """Load order details from VTEX and parse amount/currency for logging."""
    if not order_id:
        return OrderAmountDetails(amount=None, currency=None)

    account_domain = f"{vtex_account}.myvtex.com"
    try:
        order_details = vtex_io_service.get_order_details_by_id(
            account_domain=account_domain,
            vtex_account=vtex_account,
            order_id=order_id,
        )
    except Exception as exc:
        logger.warning(
            f"{log_prefix} order_lookup_failed: "
            f"vtex_account={vtex_account} order_id={order_id} error={exc}"
        )
        return OrderAmountDetails(amount=None, currency=None)

    return parse_order_amount_details(order_details)


def propagate_order_amount_to_execution_log(
    exec_logger: ExecutionLoggerServiceInterface,
    vtex_io_service: VtexIOService,
    *,
    order_id: Optional[str],
    vtex_account: str,
    log_prefix: str = "[VTEX_ORDER]",
) -> OrderAmountDetails:
    """Fetch VTEX order totals and push them onto the active execution log."""
    details = fetch_order_amount_details(
        vtex_io_service,
        order_id=order_id,
        vtex_account=vtex_account,
        log_prefix=log_prefix,
    )
    apply_order_amount_details(exec_logger, details)
    return details
