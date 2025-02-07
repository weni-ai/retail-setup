from retail.clients.base import RequestClient
from retail.interfaces.clients.vtex.interface import VtexClientInterface


class VtexClient(RequestClient, VtexClientInterface):
    """
    A client for interacting with the VTEX API.
    """

    def set_order_form_marketing_data(
        self, account_domain: str, order_form_id: str, utm_source: str
    ) -> dict:
        """
        Sets the marketing data for a specific order form.
        """
        url = f"https://{account_domain}/api/checkout/pub/orderForm/{order_form_id}/attachments/marketingData"
        payload = {"utmSource": utm_source}

        return self.make_request(url, method="POST", json=payload).json()
