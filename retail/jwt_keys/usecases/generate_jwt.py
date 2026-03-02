import jwt

from datetime import datetime, timedelta, timezone
from typing import Optional

from django.conf import settings
from retail.interfaces.jwt import JWTInterface


DEFAULT_EXPIRATION_MINUTES = 60


class JWTUsecase(JWTInterface):
    @staticmethod
    def _encode_claim(
        claim_key: str, claim_value: str, expiration_minutes: Optional[int] = None
    ) -> str:
        exp_minutes = expiration_minutes or DEFAULT_EXPIRATION_MINUTES
        payload = {
            claim_key: claim_value,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=exp_minutes),
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="RS256")

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
        return self._encode_claim(
            claim_key="project_uuid",
            claim_value=project_uuid,
            expiration_minutes=expiration_minutes,
        )

    def generate_proxy_vtex_jwt_token(
        self, vtex_account: str, expiration_minutes: Optional[int] = None
    ) -> str:
        """
        Generate JWT token for VTEX IO proxy route using vtex_account.

        This is intentionally scoped for proxy-vtex flow so the default
        project_uuid-based token remains unchanged for other contexts.
        """
        return self._encode_claim(
            claim_key="vtex_account",
            claim_value=vtex_account,
            expiration_minutes=expiration_minutes,
        )
