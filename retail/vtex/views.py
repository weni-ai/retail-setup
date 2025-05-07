from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.utils.aws.lambda_validator import LambdaURLValidator
from retail.vtex.serializers import OrdersQueryParamsSerializer
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.get_orders import GetOrdersUsecase


class OrdersProxyView(APIView, LambdaURLValidator):
    """
    POST endpoint that proxies query parameters to VTEX IO OMS API.
    """

    authentication_classes = []

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
        validation_response = self.protected_resource(request)
        if validation_response.status_code != 200:
            return validation_response

        serializer = OrdersQueryParamsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = self.get_orders_usecase.execute(data=serializer.validated_data)
        return Response(result, status=status.HTTP_200_OK)
