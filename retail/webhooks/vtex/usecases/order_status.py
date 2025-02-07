from retail.features.models import IntegratedFeature


class OrderStatusUseCase:
    """
    Use case for handling order status updates.
    """

    @classmethod
    def get_domain_by_account(cls, account: str) -> str:
        """
        Get the domain for a given account.
        """
        return f"https://{account}.vtexcommercestable.com.br"

    @classmethod
    def get_template_by_order_status(
        cls, integrated_feature: IntegratedFeature, order_status: str
    ):
        """
        Get the template for a given order status.
        """
        order_status_templates = integrated_feature.config.get(
            "order_status_templates", {}
        )

        return order_status_templates.get(order_status, "")

    @classmethod
    def process_notification(self, domain: str, order_id: str, template: str):
        """
        Process the order status notification.
        """
        # TODO
