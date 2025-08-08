from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.internal.jwt_mixins import JWTModuleAuthMixin

from retail.vtex.dtos.register_order_form_dto import RegisterOrderFormDTO
from retail.vtex.serializers import (
    OrderFormTrackingSerializer,
    OrdersQueryParamsSerializer,
)
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.get_account_identifier import GetAccountIdentifierUsecase
from retail.vtex.usecases.get_order_detail import GetOrderDetailsUsecase
from retail.vtex.usecases.get_orders import GetOrdersUsecase
from retail.vtex.usecases.register_order_form import RegisterOrderFormUseCase


class BaseVtexProxyView(JWTModuleAuthMixin, APIView):
    """
    Base class for all VTEX proxy views.

    Includes shared behaviors like JWT authentication.
    """


class OrdersProxyView(BaseVtexProxyView):
    """
    POST endpoint that proxies query parameters to VTEX IO OMS API.
    """

    def __init__(self, **kwargs):
        """
        Initialize the OrdersProxyView.

        Args:
            **kwargs: Additional keyword arguments passed to parent classes.
        """
        super().__init__(**kwargs)
        self._get_orders_usecase = None

    @property
    def get_orders_usecase(self) -> GetOrdersUsecase:
        """
        Lazy-loaded property that returns the GetOrdersUsecase instance.

        Returns:
            GetOrdersUsecase: An instance of the GetOrdersUsecase.
        """
        if not self._get_orders_usecase:
            self._get_orders_usecase = GetOrdersUsecase(vtex_io_service=VtexIOService())
        return self._get_orders_usecase

    def post(self, request: Request) -> Response:
        """
        Handle POST requests to proxy orders from VTEX IO OMS API.

        Args:
            request (Request): The incoming request object.

        Returns:
            Response: The API response with order data or error message.
        """
        serializer = OrdersQueryParamsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = self.get_orders_usecase.execute(
            data=serializer.validated_data, project_uuid=self.project_uuid
        )
        return Response(result, status=status.HTTP_200_OK)


class AccountIdentifierProxyView(BaseVtexProxyView):
    """
    GET endpoint to retrieve VTEX account identifier for a specific project.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._usecase = None

    @property
    def usecase(self) -> GetAccountIdentifierUsecase:
        if not self._usecase:
            self._usecase = GetAccountIdentifierUsecase(VtexIOService())
        return self._usecase

    def get(self, request: Request) -> Response:
        """
        Retrieves the VTEX account identifier using the project UUID from JWT token.

        Args:
            request (Request): The incoming HTTP request.

        Returns:
            Response: VTEX account identifier or error.
        """
        try:
            result = self.usecase.execute(project_uuid=self.project_uuid)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class OrderDetailsProxyView(BaseVtexProxyView):
    """
    GET endpoint that retrieves details for a specific order from VTEX IO OMS API.
    """

    def __init__(self, **kwargs):
        """
        Initialize the OrderDetailsProxyView.

        Args:
            **kwargs: Additional keyword arguments passed to parent classes.
        """
        super().__init__(**kwargs)
        self._get_order_details_usecase = None

    @property
    def get_order_details_usecase(self) -> GetOrderDetailsUsecase:
        """
        Lazy-loaded property that returns the GetOrderDetailsUsecase instance.

        Returns:
            GetOrderDetailsUsecase: An instance of the GetOrderDetailsUsecase.
        """
        if not self._get_order_details_usecase:
            self._get_order_details_usecase = GetOrderDetailsUsecase(
                vtex_io_service=VtexIOService()
            )
        return self._get_order_details_usecase

    def get(self, request: Request, order_id: str) -> Response:
        """
        Handle GET requests to retrieve specific order details from VTEX IO OMS API.

        Args:
            request (Request): The incoming request object.
            order_id (str): The ID of the order to retrieve details for.

        Returns:
            Response: The API response with order details or error message.
        """
        try:
            result = self.get_order_details_usecase.execute(
                order_id=order_id, project_uuid=self.project_uuid
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class OrderFormTrackingView(BaseVtexProxyView):
    """
    Link a VTEX order-form ID with the WhatsApp channel.

    This view handles the linking of a VTEX order-form ID to a WhatsApp channel
    by validating the request, deserializing the input, and executing the use case
    to register the order form.

    Authentication is handled through JWT tokens via JWTModuleAuthMixin.
    """

    def post(self, request: Request) -> Response:
        """
        Handle POST requests to link a VTEX order-form ID with a WhatsApp channel.

        Args:
            request (Request): The incoming HTTP request containing the order-form data.

        Returns:
            Response: A DRF Response containing a success message and the linked cart details,
            or an error response if validation fails.
        """
        serializer: OrderFormTrackingSerializer = OrderFormTrackingSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        dto: RegisterOrderFormDTO = RegisterOrderFormDTO(**serializer.validated_data)
        use_case: RegisterOrderFormUseCase = RegisterOrderFormUseCase(
            project_uuid=self.project_uuid
        )

        cart = use_case.execute(dto)

        return Response(
            {
                "message": "Click-ID linked successfully.",
                "cart_uuid": str(cart.uuid),
                "order_form_id": cart.order_form_id,
                "flows_channel_uuid": str(cart.flows_channel_uuid),
            },
            status=status.HTTP_200_OK,
        )
