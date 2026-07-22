from mozilla_django_oidc.contrib.drf import OIDCAuthentication
from weni_commons.auth import WeniAuthentication

from retail.internal.backends import WeniOIDCAuthenticationBackend


class InternalOIDCAuthentication(OIDCAuthentication):
    def __init__(self, backend=None):
        super().__init__(backend or WeniOIDCAuthenticationBackend())


class RetailAuthentication(WeniAuthentication):
    """Retail composition root for unified Weni authentication.

    Delegates JWT and Keycloak validation to ``weni_commons`` and injects
    the retail OIDC backend as the Keycloak fallback.

    Args:
        oidc_backend: Optional OIDC backend override, mainly for tests.
    """

    def __init__(self, oidc_backend=None):
        super().__init__(oidc_backend=oidc_backend or WeniOIDCAuthenticationBackend())
