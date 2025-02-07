from rest_framework.exceptions import ValidationError
from sentry_sdk import capture_message

from retail.features.models import IntegratedFeature
from retail.projects.models import Project
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


class OrderStatusUseCase:
    """
    Use case for handling order status updates.
    """

    def __init__(self, data: OrderStatusDTO):
        self.recorder = data.get("recorder")
        self.domain = data.get("domain")
        self.order_id = data.get("orderId")
        self.current_state = data.get("currentState")
        self.last_state = data.get("lastState")
        self.current_change_date = data.get("currentChangeDate")
        self.last_change_date = data.get("lastChangeDate")
        self.vtex_account = data.get("vtexAccount")

    @classmethod
    def _get_domain_by_account(cls, account: str) -> str:
        """
        Get the domain for a given account.
        """
        return f"https://{account}.vtexcommercestable.com.br"

    def _get_project_by_vtex_account(self, vtex_account: str) -> Project:
        """
        Get the project by VTEX account.
        """
        project = Project.objects.filter(vtex_account=vtex_account).first()

        if not project:
            error_message = f"Project not found for VTEX account {vtex_account}. Order id: {self.order_id}"
            capture_message(error_message)

            raise ValidationError(
                {"error": "Project not found for this VTEX account"},
                code="project_not_found",
            )

        return project

    def _get_integrated_feature_by_project(self, project: Project) -> IntegratedFeature:
        """
        Get the integrated feature by project.
        """
        integrated_feature = IntegratedFeature.objects.filter(
            project=project,
            feature__code="order_status",
        ).first()

        if not integrated_feature:
            error_message = f"Order status integration not found for project {project.name}. Order id: {self.order_id}"
            capture_message(error_message)

            raise ValidationError(
                {"error": "Order status integration not found"},
                code="order_status_integration_not_found",
            )

        return integrated_feature

    def _get_template_by_order_status(
        self, integrated_feature: IntegratedFeature, order_status: str
    ):
        """
        Get the template for a given order status.
        """
        order_status_templates = integrated_feature.config.get(
            "order_status_templates", {}
        )

        if not order_status_templates:
            error_message = f"Order status templates not found for project {integrated_feature.feature.project.uuid}. Order id: {self.order_id}"
            capture_message(error_message)

            raise ValidationError(
                {"error": "Order status templates not found"},
                code="order_status_templates_not_found",
            )

        return order_status_templates.get(order_status, "")

    def process_notification(self):
        """
        Process the order status notification.
        """
        project = self._get_project_by_vtex_account(self.vtex_account)
        domain = OrderStatusUseCase._get_domain_by_account(self.vtex_account)

        integrated_feature = self._get_integrated_feature_by_project(project)

        template_name = self._get_template_by_order_status(
            integrated_feature, self.current_state
        )

        if not template_name:
            error_message = f"Template not found for order status {data.get('currentState')}. Order id: {self.order_id}"
            capture_message(error_message)

            raise ValidationError(
                {
                    "error": "Template not found for this order status",
                },
                code="template_not_found",
            )

        # TODO: Send notification to the user
