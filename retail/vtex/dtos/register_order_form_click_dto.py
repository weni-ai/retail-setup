from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RegisterOrderFormClickDTO:
    """Immutable transport object with the parameters for the use case."""

    order_form_id: str
    whatsapp_click_id: str
    channel_uuid: UUID
