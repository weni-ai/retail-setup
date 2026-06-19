from dataclasses import dataclass
from typing import Optional, Union


@dataclass(frozen=True, slots=True)
class ProxyPaymentGatewayDTO:
    """Immutable transport object for the Payment Gateway proxy use case."""

    method: str
    path: str
    headers: Optional[dict] = None
    data: Optional[Union[dict, list]] = None
    params: Optional[dict] = None
