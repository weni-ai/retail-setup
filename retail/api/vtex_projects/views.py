import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.internal.jwt_mixins import JWTModuleAuthMixin
from retail.api.vtex_projects.serializers import AgentActiveQuerySerializer
from retail.api.vtex_projects.usecases.check_agent_active import (
    CheckAgentActiveUseCase,
)
from retail.api.vtex_projects.usecases.check_onboarding_complete import (
    INACTIVE_STATUS,
    CheckOnboardingCompleteUseCase,
)


logger = logging.getLogger(__name__)

INACTIVE_RESPONSE = {"is_active": False}


class AgentActiveView(JWTModuleAuthMixin, APIView):
    """
    Checks whether a specific agent type is active for a VTEX account.

    Called by the VTEX IO app before forwarding events to avoid
    unnecessary load when no agent is integrated.
    """

    def get(self, request: Request, vtex_account: str) -> Response:
        serializer = AgentActiveQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(INACTIVE_RESPONSE, status=status.HTTP_200_OK)

        agent_type = serializer.validated_data["agent"]

        try:
            use_case = CheckAgentActiveUseCase()
            is_active = use_case.execute(
                vtex_account=vtex_account,
                agent_type=agent_type,
            )
        except Exception:
            logger.exception(
                f"Unexpected error checking agent active for "
                f"vtex_account={vtex_account} agent={agent_type}"
            )
            return Response(INACTIVE_RESPONSE, status=status.HTTP_200_OK)

        return Response({"is_active": is_active}, status=status.HTTP_200_OK)


class OnboardingCompleteView(JWTModuleAuthMixin, APIView):
    """
    Checks whether the onboarding process is fully completed for a VTEX account.

    Called by the VTEX IO storefront pixel to decide whether to inject
    the Agentic CX script on the page.
    """

    def get(self, request: Request, vtex_account: str) -> Response:
        try:
            use_case = CheckOnboardingCompleteUseCase()
            result = use_case.execute(vtex_account=vtex_account)
        except Exception:
            logger.exception(
                f"Unexpected error checking onboarding complete for "
                f"vtex_account={vtex_account}"
            )
            return Response(INACTIVE_STATUS.to_dict(), status=status.HTTP_200_OK)

        return Response(result.to_dict(), status=status.HTTP_200_OK)
