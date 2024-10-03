import requests

from django.conf import settings

from retail.clients.exceptions import CustomAPIException


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
                timeout=60,
                params=params,
                files=files,
            )
        except Exception as e:
            raise CustomAPIException(
                detail=f"Base request error: {str(e)}",
                status_code=getattr(e.response, "status_code", None),
            ) from e

        if response.status_code >= 400:
            detail = ""
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise CustomAPIException(detail=detail, status_code=response.status_code)

        return response


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
