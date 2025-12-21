"""
Mixin to provide easy access to JWT payload for inter-module communication.
"""

from retail.internal.jwt_authenticators import JWTModuleAuthentication


class JWTModuleAuthMixin:
    """
    Mixin to provide easy access to JWT payload for inter-module communication.

    This mixin is designed for secure communication between modules where:
    - An intelligent agent or VTEX IO module needs to communicate
    - A JWT token with project_uuid or vtex_account is sent
    - This module receives and validates the token using the public key

    Supports tokens with either project_uuid or vtex_account in the payload.

    Usage: Inherit this in your APIView for inter-module communication.
    """

    authentication_classes = [JWTModuleAuthentication]
    permission_classes = []

    @property
    def project_uuid(self):
        """Get the project_uuid from the validated JWT token."""
        return getattr(self.request, "project_uuid", None)

    @property
    def vtex_account(self):
        """Get the vtex_account from the validated JWT token."""
        return getattr(self.request, "vtex_account", None)

    @property
    def jwt_payload(self):
        """Get the full JWT payload from the validated token."""
        return getattr(self.request, "jwt_payload", None)
