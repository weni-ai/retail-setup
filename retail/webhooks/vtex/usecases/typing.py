from typing import TypedDict


class OrderStatusDTO(TypedDict):
    recorder: dict
    domain: str
    orderId: str
    currentState: str
    lastState: str
    currentChangeDate: str
    lastChangeDate: str
    vtexAccount: str
