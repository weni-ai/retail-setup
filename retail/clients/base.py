import requests
import logging

import sentry_sdk
from django.conf import settings

from retail.clients.exceptions import CustomAPIException

logger = logging.getLogger(__name__)


class RequestClient:
    def make_request(
        self,
        url: str,
        method: str,
        headers=None,
        data=None,
        params=None,
        files=None,
        json=None,
        timeout=60,
    ):
        if data and json:
            raise ValueError(
                "Cannot use both 'data' and 'json' arguments simultaneously."
            )
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                data=data,
                timeout=timeout,
                params=params,
                files=files,
            )
        except Exception as e:
            self._log_request_exception(
                exception=e,
                url=url,
                method=method,
                headers=headers,
                json=json,
                data=data,
                params=params,
                files=files,
            )
            sentry_sdk.capture_exception(e)
            raise CustomAPIException(
                detail=f"Base request error: {str(e)}",
                status_code=getattr(e.response, "status_code", None),
            ) from e

        if response.status_code >= 400:
            self._log_http_error(
                response, url, method, headers, json, data, params, files
            )

            detail = ""
            try:
                detail = response.json()
            except ValueError:
                detail = response.text

            exc = CustomAPIException(detail=detail, status_code=response.status_code)
            if response.status_code >= 500:
                sentry_sdk.capture_exception(exc)
            raise exc

        # Handle empty responses to prevent JSON parsing errors
        if not response.text.strip():
            # Create a mock response object with empty JSON content
            response._content = b"{}"
            response.encoding = "utf-8"

        return response

    def _log_http_error(
        self, response, url, method, headers, json, data, params, files
    ):
        if response is None:
            logger.error("Response object is None, request failed.")
            return

        body = response.text[:1000] if response.text else ""
        logger.error(
            f"HTTP {response.status_code} {method.upper()} {url} — body={body}",
            extra={
                "request_details": {
                    "method": method,
                    "url": url,
                    "headers": headers,
                    "json": json,
                    "data": data,
                    "params": params,
                    "files": files,
                },
                "response_details": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text,
                    "url": response.url,
                },
            },
        )

    def _log_request_exception(
        self, exception, url, method, headers, json, data, params, files
    ):
        request_details = {
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
            "data": data,
            "params": params,
            "files": files,
        }
        exception_details = {
            "type": type(exception).__name__,
            "message": str(exception),
            "args": exception.args,
        }
        # Check if the exception has a response attribute (specific to requests exceptions)
        if hasattr(exception, "response") and exception.response is not None:
            exception_details.update(
                {
                    "response_status_code": exception.response.status_code,
                    "response_headers": dict(exception.response.headers),
                    "response_body": exception.response.text,
                }
            )

        logger.error(
            f"Request exception {type(exception).__name__} "
            f"{method.upper()} {url}: {exception}",
            exc_info=True,
            extra={
                "request_details": request_details,
                "exception_details": exception_details,
            },
        )


class InternalAuthentication(RequestClient):
    def __get_module_token(self):
        data = {
            "client_id": settings.OIDC_RP_CLIENT_ID,
            "client_secret": settings.OIDC_RP_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }
        request = self.make_request(
            url=settings.OIDC_OP_TOKEN_ENDPOINT, method="POST", data=data
        )

        token = request.json().get("access_token")

        return f"Bearer {token}"

    @property
    def headers(self):
        return {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": self.__get_module_token(),
        }

    @property
    def headers_text(self):
        return {
            "Content-Type": "text/plain",
            "Authorization": self.__get_module_token(),
        }

    def get_token(self) -> str:
        """
        Public method to retrieve just the token string (without 'Bearer ').
        Useful when passing raw tokens to external services.
        """
        return self.__get_module_token().replace("Bearer ", "")


class UserAuthentication:
    """
    Authentication class for regular users using JWT tokens.
    """

    def __init__(self, user_token: str):
        self.user_token = user_token

    @property
    def headers(self):
        return {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": f"Bearer {self.user_token}",
        }
