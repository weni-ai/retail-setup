from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RegisterOrderFormDTO:
    """Immutable transport object with the parameters for the use case."""

    order_form_id: str
    channel_uuid: UUID
