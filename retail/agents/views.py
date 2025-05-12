from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

from agents.serializers import PushAgentSerializer, ReadAgentSerializer
from agents.usecases import PushAgentUseCase, PushAgentData


class PushAgentViewSet(APIView):
    def post(self, request: Request, *args, **kwargs) -> Response:
        request_serializer = PushAgentSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        data: PushAgentData = request_serializer.data
        use_case = PushAgentUseCase()
        agents = use_case.execute(payload=data, files=request.FILES)

        response_serializer = ReadAgentSerializer(agents, many=True)

        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
