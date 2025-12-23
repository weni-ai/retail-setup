import jwt

from datetime import datetime, timedelta, timezone
from typing import Optional

from django.conf import settings
from retail.interfaces.jwt import JWTInterface


DEFAULT_EXPIRATION_MINUTES = 60


class JWTUsecase(JWTInterface):
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
        exp_minutes = expiration_minutes or DEFAULT_EXPIRATION_MINUTES
        payload = {
            "project_uuid": project_uuid,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=exp_minutes),
            "iat": datetime.now(timezone.utc),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="RS256")
        return token
