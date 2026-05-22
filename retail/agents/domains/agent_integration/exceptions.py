from rest_framework.exceptions import APIException
from rest_framework import status


class GlobalRuleBadRequest(APIException):
    status_code = status.HTTP_400_BAD_REQUEST


class GlobalRuleUnprocessableEntity(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class GlobalRuleInternalServerError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class DirectSendTemplateUnavailableError(APIException):
    """Raised at agent-assignment time when neither the project-resolved
    language nor the pt_BR fallback returns usable content for a
    required template (FR-003d).
    """

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
    """Raised at agent-assignment time when Meta's library catalog
    returns a template whose components are outside the Direct Send
    supported set (Decision 12 — defensive).
    """

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
