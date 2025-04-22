from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status


from retail.vtex.serializers import OrdersQueryParamsSerializer
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.get_orders import GetOrdersUsecase


class OrdersProxyView(APIView):
    """
    POST endpoint that proxies query parameters to VTEX IO OMS API.
    """

    authentication_classes = []

    def post(self, request: Request) -> Response:
        """
        Handle POST requests to proxy orders from VTEX IO OMS API.
        """
        serializer = OrdersQueryParamsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        usecase = GetOrdersUsecase(vtex_io_service=VtexIOService())
        result = usecase.execute(data=serializer.validated_data)

        return Response(result, status=status.HTTP_200_OK)
