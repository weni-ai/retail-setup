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
        serializer = CartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        print(f"serializer is valid: {serializer.validated_data}")

        validated_data = serializer.validated_data
        account = validated_data["account"]
        cart_id = validated_data["cart_id"]
        phone = PhoneNumberNormalizer.normalize(validated_data["phone"])
        print(f"account: {account}\ncart_id: {cart_id}\nphone: {phone}")
        cart_use_case = CartUseCase(account=account)
        print("cart usecase created!")
        result = cart_use_case.process_cart_notification(cart_id, phone)
        print(f"result: {result}")
        return Response(
            {
                "message": "Cart processed successfully.",
                "cart_uuid": str(result.uuid),
                "cart_id": str(result.cart_id),
                "status": result.status,
            },
            status=status.HTTP_200_OK,
        )
