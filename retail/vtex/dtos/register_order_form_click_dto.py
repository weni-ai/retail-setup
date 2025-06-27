from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegisterOrderFormClickDTO:
    """Immutable transport object with the parameters for the use case."""

    order_form_id: str
    whatsapp_click_id: str
