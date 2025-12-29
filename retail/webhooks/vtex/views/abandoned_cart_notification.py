import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from retail.internal.permissions import CanCommunicateInternally
from retail.webhooks.vtex.serializers import CartSerializer
from retail.webhooks.vtex.usecases.cart import CartUseCase
from retail.vtex.usecases.phone_number_normalizer import PhoneNumberNormalizer


logger = logging.getLogger(__name__)


class AbandonedCartNotification(APIView):
    """
    Handle abandoned cart notifications.
    """

    permission_classes = [CanCommunicateInternally]

    def post(self, request):
        serializer = CartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        order_form_id = validated_data["cart_id"]
        phone = PhoneNumberNormalizer.normalize(validated_data["phone"])
        name = validated_data["name"]
        account = validated_data["account"]

        # Log context for tracking
        log_context = f"vtex_account={account} order_form={order_form_id} phone={phone}"

        logger.info(
            f"[CART_WEBHOOK] Received abandoned cart notification: {log_context}"
        )

        # Instantiate the use case with the given account
        cart_use_case = CartUseCase(account=account)

        if cart_use_case.project is None:
            logger.warning(
                f"[CART_WEBHOOK] Project not found: {log_context} - "
                f"reason=no_project_for_vtex_account"
            )
            return Response(
                {"message": "Project not found for the given account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        project_uuid = str(cart_use_case.project.uuid)
        log_context = f"{log_context} project_uuid={project_uuid}"

        # Check if either integrated agent or integrated feature is configured
        if not cart_use_case.integrated_agent and not cart_use_case.integrated_feature:
            logger.info(
                f"[CART_WEBHOOK] Integration not configured: {log_context} - "
                f"reason=no_integrated_agent_or_feature"
            )
            return Response(
                {
                    "message": "Abandoned cart integration not configured for this account."
                },
                status=status.HTTP_202_ACCEPTED,
            )

        # Log which integration type is being used
        integration_type = "agent" if cart_use_case.integrated_agent else "feature"
        integration_uuid = str(
            cart_use_case.integrated_agent.uuid
            if cart_use_case.integrated_agent
            else cart_use_case.integrated_feature.uuid
        )
        logger.info(
            f"[CART_WEBHOOK] Processing cart: {log_context} "
            f"integration_type={integration_type} integration_uuid={integration_uuid}"
        )

        # Proceed with cart notification processing
        result = cart_use_case.process_cart_notification(order_form_id, phone, name)

        logger.info(
            f"[CART_WEBHOOK] Cart processed: {log_context} "
            f"cart_uuid={result.uuid} cart_status={result.status}"
        )

        return Response(
            {
                "message": "Cart processed successfully.",
                "cart_uuid": str(result.uuid),
                "cart_id": str(result.order_form_id),
                "status": result.status,
            },
            status=status.HTTP_200_OK,
        )
