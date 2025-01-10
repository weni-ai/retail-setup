from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from retail.internal.permissions import CanCommunicateInternally
from retail.webhooks.vtex.serializers import CartSerializer
from retail.webhooks.vtex.usecases.cart import CartUseCase
from retail.vtex.usecases.phone_number_normalizer import PhoneNumberNormalizer


class AbandonedCartNotification(APIView):
    """
    Handle abandoned cart notifications.
    """
    permission_classes = [CanCommunicateInternally]

    def post(self, request):
        # Validação dos dados recebidos
        serializer = CartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Extrai dados validados
        validated_data = serializer.validated_data
        account = validated_data["account"]
        cart_id = validated_data["cart_id"]
        store = validated_data["store"]
        phone = PhoneNumberNormalizer.normalize(validated_data["phone"])

        # Processa a notificação
        cart_use_case = CartUseCase(account=account)
        result = cart_use_case.process_cart_notification(cart_id, phone, store)

        return Response(
            {
                "message": "Cart processed successfully.",
                "cart_uuid": str(result.uuid),
                "cart_id": str(result.cart_id),
                "status": result.status,
            },
            status=status.HTTP_200_OK,
        )
