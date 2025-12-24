from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.internal.jwt_mixins import JWTModuleAuthMixin
from retail.webhooks.vtex.serializers import CartSerializer
from retail.webhooks.vtex.usecases.cart import CartUseCase
from retail.vtex.usecases.phone_number_normalizer import PhoneNumberNormalizer


class AbandonedCartNotification(JWTModuleAuthMixin, APIView):
    """
    Handle abandoned cart notifications.

    Expects JWT token with vtex_account in the payload.
    """

    def post(self, request: Request):
        serializer = CartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        order_form_id = validated_data["cart_id"]
        phone = PhoneNumberNormalizer.normalize(validated_data["phone"])
        name = validated_data["name"]

        # Instantiate the use case with the given account
        cart_use_case = CartUseCase(account=validated_data["account"])

        if cart_use_case.project is None:
            return Response(
                {"message": "Project not found for the given account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the abandoned cart feature is integrated for the project
        if not cart_use_case.integrated_feature:
            return Response(
                {
                    "message": "Abandoned cart integration not configured for this account."
                },
                status=status.HTTP_202_ACCEPTED,
            )

        # Proceed with cart notification processing
        result = cart_use_case.process_cart_notification(order_form_id, phone, name)

        return Response(
            {
                "message": "Cart processed successfully.",
                "cart_uuid": str(result.uuid),
                "cart_id": str(result.order_form_id),
                "status": result.status,
            },
            status=status.HTTP_200_OK,
        )
