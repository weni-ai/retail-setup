from mozilla_django_oidc.contrib.drf import OIDCAuthentication

from retail.internal.backends import WeniOIDCAuthenticationBackend


class InternalOIDCAuthentication(OIDCAuthentication):
    def __init__(self, backend=None):
        super().__init__(backend or WeniOIDCAuthenticationBackend())
