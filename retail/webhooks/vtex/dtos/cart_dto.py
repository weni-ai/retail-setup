from typing import Dict
from dataclasses import dataclass


@dataclass
class CartDTO:
    """
    Data Transfer Object (DTO) for handling cart data.
    """
    action: str  # The action to perform, e.g., 'create', 'update', etc.
    account: str  # The VTEX account identifier
    home_phone: str  # The user's phone number
    data: Dict  # The cart details to be stored in the model
