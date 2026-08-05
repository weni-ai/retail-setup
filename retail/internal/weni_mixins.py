from weni_commons.auth import WeniAuthViewMixin

from retail.internal.authenticators import RetailAuthentication


class WeniAuthMixin(WeniAuthViewMixin):
    """Retail wiring for unified JWT + Keycloak authentication.

    Binds ``RetailAuthentication`` as the view's authenticator and inherits the
    ``IsWeniAuthenticated`` permission from ``WeniAuthViewMixin``. Views read
    identity and tenant scope (``vtex_account`` / ``project_uuid``) exclusively
    from ``self.auth``, which raises ``403`` when a required field is absent.
    """

    authentication_classes = [RetailAuthentication]
