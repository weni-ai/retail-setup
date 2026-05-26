from typing import Any, Dict, Optional

from rest_framework.exceptions import APIException
from rest_framework import status


class IntegrationsServerError(APIException):
    default_detail = "Unable to access Integrations API."


class CustomTemplateAlreadyExists(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class NotDirectSendEligibleError(Exception):
    """Raised when the template's IntegratedAgent does not have
    ``direct_send`` enabled per FR-002a.

    The view translates this exception to HTTP 400 with body
    ``{"detail": "Template is not Direct Send-eligible",
    "error_code": "not_direct_send_eligible"}`` per FR-007e.
    """


class WabaNotConfiguredError(Exception):
    """Raised when the project's ``ProjectOnboarding`` config does not
    carry a ``wpp-cloud`` channel's ``waba_id`` per FR-005a.

    The view translates this exception to HTTP 400 with body
    ``{"detail": "WABA not configured for this project",
    "error_code": "waba_not_configured"}`` per FR-007d.
    """


class MetaSampleUnavailableError(Exception):
    """Raised when the outbound Meta ``message_samples`` call failed
    (``CustomAPIException`` or an unexpected exception) per FR-005c.

    Carries the original HTTP status code (when known) and the raw
    Meta error envelope so the view can surface them on the HTTP 502
    response body per FR-007b.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        meta_response: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.meta_response = meta_response


class MetaInvalidResponseError(Exception):
    """Raised when Meta returned HTTP 200 but the body lacks a
    ``category`` field or carries ``success: false`` per FR-005b.

    Carries the raw Meta response body verbatim so the view can
    surface it on the HTTP 502 response body per FR-007b.
    """

    def __init__(
        self,
        message: str,
        *,
        meta_response: Dict[str, Any],
    ):
        super().__init__(message)
        self.meta_response = meta_response
