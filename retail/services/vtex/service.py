from retail.interfaces.clients.vtex.interface import VtexClientInterface


class VtexService:
    def __init__(self, client: VtexClientInterface):
        self.client = client

    def set_order_form_marketing_data(
        self, account_domain: str, order_form_id: str, utm_source: str
    ) -> dict:
        self.client.set_order_form_marketing_data(
            account_domain,
            order_form_id,
            utm_source,
        )
