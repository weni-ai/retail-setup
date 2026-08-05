import jwt

from typing import Optional, Tuple, Any

from rest_framework.exceptions import AuthenticationFailed
from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request
from django.conf import settings


class JWTModuleAuthentication(BaseAuthentication):
    """
    DRF authentication class for inter-module communication using JWT tokens.

    This class handles JWT authentication for secure communication between modules:
    - Validates the JWT signature using the public key from settings
    - Extracts 'project_uuid' or 'vtex_account' from the payload
    - Supports Authorization header with or without 'Bearer' prefix

    Usage:
        authentication_classes = [JWTModuleAuthentication]
    """

    def _extract_token(self, request: Request) -> str:
        """Extract JWT token from Authorization header."""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header:
            raise AuthenticationFailed("Missing Authorization header.")

        if auth_header.startswith("Bearer "):
            return auth_header.split(" ", 1)[1]
        return auth_header

    def authenticate(self, request: Request) -> Optional[Tuple[Any, None]]:
        """Authenticate the request using a JWT for inter-module communication.

        Args:
            request: Incoming DRF request with an Authorization header.

        Returns:
            A tuple of ``(None, None)`` because inter-module JWT auth does not
            bind a Django user or DRF auth object. Validated claims are
            attached to the request as ``project_uuid``, ``vtex_account``,
            and ``jwt_payload``.

        Raises:
            AuthenticationFailed: When the public key is missing, the token
                is invalid or expired, or required claims are absent.
        """
        public_key: Optional[bytes] = getattr(settings, "JWT_PUBLIC_KEY", None)
        if not public_key:
            raise AuthenticationFailed(
                "JWT_PUBLIC_KEY not configured in Django settings. "
                "Please add the public key for JWT validation."
            )

        token = self._extract_token(request)

        try:
            payload: dict = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token expired.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token.")

        project_uuid: Optional[str] = payload.get("project_uuid")
        vtex_account: Optional[str] = payload.get("vtex_account")

        if not project_uuid and not vtex_account:
            raise AuthenticationFailed(
                "Token must contain 'project_uuid' or 'vtex_account'."
            )

        request.project_uuid = project_uuid
        request.vtex_account = vtex_account
        request.jwt_payload = payload

        return (None, None)
