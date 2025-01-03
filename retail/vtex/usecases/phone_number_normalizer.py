import re
from rest_framework.exceptions import ValidationError


class PhoneNumberNormalizer:
    """
    Helper class to normalize phone numbers into the format: CC DDD NUMBER
    """

    @staticmethod
    def normalize(phone_number: str) -> str:
        """
        Normalize a phone number to the format CC DDD NUMBER (e.g., 5584987654321).

        Args:
            phone_number (str): The phone number to normalize.

        Returns:
            str: The normalized phone number.

        Raises:
            ValidationError: If the phone number cannot be normalized.
        """
        # Check if the number is empty or censored (contains '*')
        if not phone_number or "*" in phone_number:
            raise ValidationError(f"Invalid or censored phone number: {phone_number}")

        # Remove all non-numeric characters except the leading "+"
        phone_number = re.sub(r"[^\d+]", "", phone_number)

        # Remove multiple "+" and keep only one at the beginning (if present)
        if phone_number.startswith("++"):
            phone_number = phone_number.lstrip("+")

        # Remove any remaining "+" and keep only digits
        phone_number = phone_number.lstrip("+")

        # Validate if the number has at least 10 digits (CC + DDD + Number)
        if len(phone_number) < 10:
            raise ValidationError(f"Invalid phone number length: {phone_number}")

        return phone_number
