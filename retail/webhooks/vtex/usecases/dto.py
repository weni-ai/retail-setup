from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessAbandonedCartNotificationDTO:
    order_form_id: str
    phone: str
    name: str


@dataclass(frozen=True)
class ProcessBackInStockNotificationDTO:
    sku_id: str
    phone: str
    name: str
    locale: str


@dataclass(frozen=True)
class EnqueueBackInStockNotificationsDTO:
    account: str
    shoppers: tuple[ProcessBackInStockNotificationDTO, ...]


@dataclass(frozen=True)
class BackInStockLambdaPayload:
    """Minimum payload ActiveAgent.invoke needs besides injected project.

    The lambda looks up the SKU and returns ``template``, SKU name,
    ``image_url`` and the add-to-cart ``button`` path. ``store`` is the
    shopper-facing origin used to build that cart URL. ``phone_number``
    is for WhatsApp send only and must never be logged.
    """

    sku_id: str
    client_name: str
    phone_number: str
    store: str

    def to_lambda_dict(self) -> dict:
        return {
            "sku_id": self.sku_id,
            "client_name": self.client_name,
            "phone_number": self.phone_number,
            "store": self.store,
        }


@dataclass(frozen=True)
class ProcessBackInStockNotificationResult:
    discarded: bool
    reason: str


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
