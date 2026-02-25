from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework.permissions import IsAuthenticated

from retail.internal.authenticators import InternalOIDCAuthentication


class InternalGenericViewSet(GenericViewSet):
    authentication_classes = [InternalOIDCAuthentication]
    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer]
    throttle_classes = []


class KeycloakAPIView(APIView):
    """Base APIView with Keycloak (OIDC) authentication."""

    authentication_classes = [InternalOIDCAuthentication]
    permission_classes = [IsAuthenticated]
