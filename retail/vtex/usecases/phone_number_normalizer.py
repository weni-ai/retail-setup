import re


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
            ValueError: If the phone number cannot be normalized.
        """
        if not phone_number:
            raise ValueError("Phone number cannot be empty.")

        # Remove non-numeric characters except the leading "+"
        phone_number = re.sub(r"[^\d+]", "", phone_number)

        # Ensure there is only one "+" at the beginning (if any)
        if phone_number.startswith("++"):
            phone_number = phone_number.lstrip("+")

        # Remove "+" and ensure only digits are left
        phone_number = phone_number.lstrip("+")

        # Validate the resulting number length (minimum CC + DDD + NUMBER)
        if len(phone_number) < 10:
            raise ValueError(f"Invalid phone number: {phone_number}")

        return phone_number
