from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.utils.aws.lambda_validator import LambdaURLValidator
from retail.vtex.serializers import OrdersQueryParamsSerializer
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.get_account_identifier import GetAccountIdentifierUsecase
from retail.vtex.usecases.get_order_detail import GetOrderDetailsUsecase
from retail.vtex.usecases.get_orders import GetOrdersUsecase


class BaseVtexProxyView(APIView, LambdaURLValidator):
    """
    Base class for all VTEX proxy views.

    Includes shared behaviors like Lambda STS validation and
    default settings for authentication.
    """

    authentication_classes = []

    def validate_lambda(self, request: Request) -> Response | None:
        """
        Validates the request against the Lambda URL validator.

        Args:
            request (Request): The incoming request.

        Returns:
            Optional[Response]: Error response if validation fails, else None.
        """
        validation_response = self.protected_resource(request)
        if validation_response.status_code != 200:
            return validation_response
        return None


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
        # AWS Lambda STS validation
        error_response = self.validate_lambda(request)
        if error_response:
            return error_response

        serializer = OrdersQueryParamsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = self.get_orders_usecase.execute(data=serializer.validated_data)
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

    def get(self, request: Request, project_uuid: str) -> Response:
        """
        Retrieves the VTEX account identifier using the project UUID from the URL.

        Args:
            request (Request): The incoming HTTP request.
            project_uuid (str): The UUID of the project.

        Returns:
            Response: VTEX account identifier or error.
        """
        error_response = self.validate_lambda(request)
        if error_response:
            return error_response

        try:
            result = self.usecase.execute(project_uuid)
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

    def get(self, request: Request, project_uuid: str, order_id: str) -> Response:
        """
        Handle GET requests to retrieve specific order details from VTEX IO OMS API.

        Args:
            request (Request): The incoming request object.
            project_uuid (str): The UUID of the project associated with the order.
            order_id (str): The ID of the order to retrieve details for.

        Returns:
            Response: The API response with order details or error message.
        """
        error_response = self.validate_lambda(request)
        if error_response:
            return error_response

        try:
            result = self.get_order_details_usecase.execute(
                project_uuid=str(project_uuid), order_id=order_id
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
