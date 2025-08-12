from typing import Protocol


class JWTInterface(Protocol):
    """Interface for JWT token generation."""

    def generate_jwt_token(self, project_uuid: str) -> str:
        """Generate JWT token for project UUID."""
        ...
