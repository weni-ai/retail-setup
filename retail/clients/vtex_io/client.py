"""Client for connection with Vtex IO"""

from django.conf import settings

from retail.clients.base import RequestClient
from retail.interfaces.clients.vtex_io.interface import VtexIOClientInterface


class InternalVtexIOAuthentication(RequestClient):
    def __get_module_token(self):
        data = {
            "client_id": settings.VTEX_IO_OIDC_RP_CLIENT_ID,
            "client_secret": settings.VTEX_IO_OIDC_RP_CLIENT_SECRET,
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


class VtexIOClient(RequestClient, VtexIOClientInterface):
    def __init__(self):
        self.authentication_instance = InternalVtexIOAuthentication()

    def get_order_form_details(self, account_domain: str, order_form_id: str) -> dict:
        url = f"https://{account_domain}/_v/order-form-details"
        params = {"orderFormId": order_form_id}
        response = self.make_request(
            url,
            method="GET",
            params=params,
            headers=self.authentication_instance.headers,
        )
        return response.json()

    def get_order_details(self, account_domain: str, user_email: str) -> dict:
        url = f"https://{account_domain}/_v/orders-by-email"
        params = {"user_email": user_email}
        response = self.make_request(
            url,
            method="GET",
            params=params,
            headers=self.authentication_instance.headers,
        )
        return response.json()
