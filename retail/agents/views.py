from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

from retail.agents.serializers import PushAgentSerializer, ReadAgentSerializer
from retail.agents.usecases import PushAgentUseCase, PushAgentData
from retail.agents.tasks import validate_pre_approved_templates


class PushAgentViewSet(APIView):
    def post(self, request: Request, *args, **kwargs) -> Response:
        request_serializer = PushAgentSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        data: PushAgentData = request_serializer.data
        use_case = PushAgentUseCase()
        agents = use_case.execute(payload=data, files=request.FILES)

        agent_ids = [str(agent.uuid) for agent in agents]
        validate_pre_approved_templates.delay(agent_ids)

        response_serializer = ReadAgentSerializer(agents, many=True)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
