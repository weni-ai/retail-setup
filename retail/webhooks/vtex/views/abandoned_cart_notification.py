from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.internal.jwt_mixins import JWTModuleAuthMixin
from retail.webhooks.vtex.serializers import CartSerializer
from retail.webhooks.vtex.usecases.dto import ProcessAbandonedCartNotificationDTO
from retail.webhooks.vtex.usecases.exceptions import (
    IntegrationNotConfiguredError,
    ProjectNotFoundError,
)
from retail.webhooks.vtex.usecases.process_abandoned_cart_notification import (
    ProcessAbandonedCartNotificationUseCase,
)


class AbandonedCartNotification(JWTModuleAuthMixin, APIView):
    """
    Handle abandoned cart notifications.

    Expects JWT token with vtex_account in the payload.
    """

    def post(self, request: Request):
        serializer = CartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        dto = ProcessAbandonedCartNotificationDTO(
            order_form_id=validated_data["cart_id"],
            phone=validated_data["phone"],
            name=validated_data["name"],
        )
        account = validated_data["account"]

        try:
            result = ProcessAbandonedCartNotificationUseCase.from_vtex_account(
                account
            ).execute(dto)
        except ProjectNotFoundError:
            return Response(
                {"message": "Project not found for the given account."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except IntegrationNotConfiguredError:
            return Response(
                {
                    "message": (
                        "Abandoned cart integration not configured for this account."
                    )
                },
                status=status.HTTP_202_ACCEPTED,
            )

        return Response(result.to_dict(), status=status.HTTP_200_OK)
