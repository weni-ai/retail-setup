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


@dataclass
class CartAbandonmentDataDTO:
    """
    Complete cart abandonment data structure for both agent and legacy flows.
    """

    # Cart basic info
    cart_uuid: str
    order_form_id: str
    phone_number: str
    project_uuid: str
    vtex_account: str

    # Client info
    client_name: str
    client_profile: Dict[str, Any]
    locale: str

    # Cart content
    cart_items: List[Dict[str, Any]]
    total_value: float

    # Order form data
    order_form: Dict[str, Any]

    # Configuration (only for legacy flow - agent flow gets these from AWS Lambda)
    template_name: str = None
    channel_uuid: str = None

    # Additional data
    cart_link: str = ""
    additional_data: Dict[str, Any] = None
