from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class ProxyPaymentTransactionDTO:
    """Immutable transport object for the payment transaction proxy use case."""

    transaction_id: str
    payments: tuple
    merchant_name: Optional[str] = None
