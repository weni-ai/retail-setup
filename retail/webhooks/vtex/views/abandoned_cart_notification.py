from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from retail.webhooks.vtex.serializers import CartSerializer
from retail.webhooks.vtex.dtos.cart_dto import CartDTO
from retail.webhooks.vtex.usecases.cart import CartUseCase


class AbandonedCartNotification(APIView):
    """
    View to handle abandoned cart notifications.

    This view receives data from the VTEX IO middleware,
    processes it, and performs necessary actions.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        cart_dto = CartDTO(
            action=validated_data["action"],
            account=validated_data["account"],
            home_phone=validated_data["homePhone"],
            data=validated_data["data"],
        )

        cart_use_case = CartUseCase(account=cart_dto.account)
        result = cart_use_case.handle_action(cart_dto.action, cart_dto)

        return Response(
            {
                "message": f"Cart action '{cart_dto.action}' processed successfully.",
                "cart_id": str(result.uuid),
                "status": result.status,
            },
            status=status.HTTP_200_OK,
        )
