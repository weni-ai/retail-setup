from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessAbandonedCartNotificationDTO:
    order_form_id: str
    phone: str
    name: str


@dataclass(frozen=True)
class ProcessAbandonedCartNotificationResult:
    cart_uuid: str
    cart_id: str
    status: str
    integration_type: str
    integration_uuid: str
    project_uuid: str
    vtex_account: str

    def to_dict(self) -> dict:
        """Convert result to dictionary for the JWT API success response."""
        return {
            "message": "Cart processed successfully.",
            "cart_uuid": self.cart_uuid,
            "cart_id": self.cart_id,
            "status": self.status,
        }
