from typing import Protocol, Optional


class JWTInterface(Protocol):
    """Interface for JWT token generation."""

    def generate_jwt_token(
        self, project_uuid: str, expiration_minutes: Optional[int] = None
    ) -> str:
        """
        Generate JWT token for project UUID.

        Args:
            project_uuid: The project UUID to include in the token payload.
            expiration_minutes: Optional token expiration time in minutes.
                               If not provided, uses default (60 minutes).

        Returns:
            The encoded JWT token string.
        """
        ...
