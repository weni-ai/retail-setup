from abc import ABC, abstractmethod


class VtexClientInterface(ABC):
    @abstractmethod
    def set_order_form_marketing_data(
        self, account_domain: str, order_form_id: str, utm_source: str
    ) -> dict:
        pass
