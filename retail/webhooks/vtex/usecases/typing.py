from dataclasses import dataclass
from typing import Dict


@dataclass
class OrderStatusDTO:
    recorder: Dict
    domain: str
    orderId: str
    currentState: str
    lastState: str
    currentChangeDate: str
    lastChangeDate: str
    vtexAccount: str
