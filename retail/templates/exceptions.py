from typing import Any, Dict, Optional

from rest_framework.exceptions import APIException
from rest_framework import status


class IntegrationsServerError(APIException):
    default_detail = "Unable to access Integrations API."


class CustomTemplateAlreadyExists(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class NotDirectSendEligibleError(Exception):
    """Template's IntegratedAgent has no ``direct_send``. Anchor: FR-002a."""


class WabaNotConfiguredError(Exception):
    """Project channel has no ``waba_id``. Anchor: FR-005a."""


class MetaSampleUnavailableError(Exception):
    """Meta ``message_samples`` call failed. Anchor: FR-005c."""

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
    """Meta returned 200 with no usable ``category``. Anchor: FR-005b."""

    def __init__(
        self,
        message: str,
        *,
        meta_response: Dict[str, Any],
    ):
        super().__init__(message)
        self.meta_response = meta_response
