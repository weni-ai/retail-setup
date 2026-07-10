"""Helpers for building VTEX payment recovery (PIX) order hooks."""

from typing import Any, Dict, List, Optional

DEFAULT_SALES_CHANNELS: List[str] = ["1"]
PIX_PAYMENT_SYSTEM_ID = "125"
VTEX_HOOK_USER_AGENT = "vtex-retail/0.0.0"


def build_sales_channel_clause(sales_channels: List[str]) -> Optional[str]:
    """Build the VTEX filter clause for one or more sales channels.

    Returns ``None`` when ``sales_channels`` is empty so callers can omit
    the sales-channel constraint from the hook expression.
    """
    if not sales_channels:
        return None

    if len(sales_channels) == 1:
        return f'(salesChannel = "{sales_channels[0]}")'

    channel_checks = " or ".join(
        f'salesChannel = "{channel}"' for channel in sales_channels
    )
    return f"({channel_checks})"


def build_payment_recovery_hook_expression(sales_channels: List[str]) -> str:
    """Build the VTEX ``FromOrders`` hook filter expression for PIX recovery.

    An empty ``sales_channels`` list means no sales-channel constraint: only
    the PIX payment-system filter is applied, matching VTEX accounts that do
    not segment orders by sales channel.
    """
    payment_clause = (
        "paymentData.transactions.payments"
        f'[paymentSystem = "{PIX_PAYMENT_SYSTEM_ID}"]'
    )

    if not sales_channels:
        return payment_clause

    sales_channel_clause = build_sales_channel_clause(sales_channels)
    return " and ".join(["isCompleted = false", sales_channel_clause, payment_clause])


def build_payment_recovery_hook_payload(
    webhook_url: str,
    sales_channels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build the VTEX hook configuration payload for payment recovery."""
    channels = DEFAULT_SALES_CHANNELS if sales_channels is None else sales_channels
    return {
        "filter": {
            "type": "FromOrders",
            "expression": build_payment_recovery_hook_expression(channels),
            "disableSingleFire": False,
        },
        "hook": {
            "url": webhook_url,
            "headers": {"User-Agent": VTEX_HOOK_USER_AGENT},
        },
    }
