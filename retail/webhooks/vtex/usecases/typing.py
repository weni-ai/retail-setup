from dataclasses import dataclass
from typing import Dict, List, Any


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


@dataclass
class AbandonedCartDTO:
    cart_uuid: str
    order_form_id: str
    phone_number: str
    client_name: str
    project_uuid: str
    vtex_account: str
    cart_items: List[Dict[str, Any]]
    total_value: float
    additional_data: Dict[str, Any]
