from rest_framework.exceptions import APIException
from rest_framework import status


class GlobalRuleBadRequest(APIException):
    status_code = status.HTTP_400_BAD_REQUEST


class GlobalRuleUnprocessableEntity(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class GlobalRuleInternalServerError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class DirectSendTemplateUnavailableError(APIException):
    """Raised when neither the project locale nor the ``pt_BR`` fallback
    returns usable content. Anchor: FR-003d (see
    ``specs/002-direct-send-broadcasts/spec.md``)."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "direct_send_template_unavailable"

    def __init__(
        self,
        *,
        template_name: str,
        requested_language: str,
        fallback_language: str,
        reason: str,
    ):
        self.template_name = template_name
        self.requested_language = requested_language
        self.fallback_language = fallback_language
        self.reason = reason
        detail = (
            f"Template {template_name} is not available in {requested_language} "
            f"or fallback locale {fallback_language}: {reason}"
        )
        super().__init__(detail=detail, code=self.default_code)


class DirectSendUnsupportedComponentError(APIException):
    """Raised when a library-catalog template carries components outside
    the Direct Send supported set. Anchor: Decision 12 (see
    ``specs/002-direct-send-broadcasts/spec.md``)."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "direct_send_unsupported_component"

    def __init__(self, *, template_name: str, component_type: str):
        self.template_name = template_name
        self.component_type = component_type
        detail = (
            f"Template {template_name} uses unsupported component "
            f"for Direct Send: {component_type}"
        )
        super().__init__(detail=detail, code=self.default_code)
