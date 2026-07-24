import logging
from typing import Optional
from uuid import UUID

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from retail.contracts.exceptions import (
    ContractTemplateNotFoundError,
    ProjectNotFoundError,
)
from retail.contracts.serializers import (
    ContractAcceptanceResponseSerializer,
    RegisterContractAcceptanceSerializer,
)
from retail.contracts.usecases.register_contract_acceptance import (
    RegisterContractAcceptanceDTO,
    RegisterContractAcceptanceUseCase,
)
from retail.internal.weni_mixins import WeniAuthMixin

logger = logging.getLogger(__name__)


class RegisterContractAcceptanceView(WeniAuthMixin, APIView):
    """Records an immutable contract acceptance for the authenticated user.

    Technical evidence is captured from the request itself. The client
    payload carries the subscriber identity (``user_id``, ``email_at_acceptance``),
    chosen plan, acceptance method and the exact label shown. The tenant
    (``vtex_account``) is read from the authenticated context, never from the
    body. Acceptance timestamp, local offset and contract version are resolved
    server-side.
    """

    def post(self, request: Request) -> Response:
        serializer = RegisterContractAcceptanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        dto = RegisterContractAcceptanceDTO(
            user_id=str(validated["user_id"]),
            email_at_acceptance=validated["email_at_acceptance"],
            user_name=validated["user_name"],
            company_name=validated.get("company_name") or None,
            vtex_account=self.auth.vtex_account,
            plan=validated["plan"],
            acceptance_method=validated["acceptance_method"],
            checkbox_label_text=validated["checkbox_label_text"],
            ip_address=self._client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            session_id=self._session_id(request),
            request_id=self._request_id(request),
            geo_country=None,
        )

        try:
            acceptance = RegisterContractAcceptanceUseCase().execute(dto)
        except (ProjectNotFoundError, ContractTemplateNotFoundError) as exc:
            raise NotFound(str(exc))

        return Response(
            ContractAcceptanceResponseSerializer(acceptance).data,
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    @staticmethod
    def _session_id(request: Request) -> str:
        header_session = request.META.get("HTTP_X_SESSION_ID")
        if header_session:
            return header_session
        return request.session.session_key or ""

    @staticmethod
    def _request_id(request: Request) -> Optional[str]:
        raw = request.META.get("HTTP_X_REQUEST_ID")
        if not raw:
            return None
        try:
            return str(UUID(raw))
        except ValueError:
            return None
