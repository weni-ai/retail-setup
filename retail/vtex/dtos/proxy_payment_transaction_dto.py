from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProxyPaymentTransactionDTO:
    """Immutable transport object for the payment transaction proxy use case."""

    transaction_id: str
    payments: tuple
