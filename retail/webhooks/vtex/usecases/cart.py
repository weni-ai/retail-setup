import logging

from rest_framework.exceptions import ValidationError, NotFound
from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.vtex.tasks import mark_cart_as_abandoned

from retail.webhooks.vtex.services import CartTimeRestrictionService


logger = logging.getLogger(__name__)


def generate_task_key(cart_uuid: str) -> str:
    """
    Generate a deterministic task key using the cart UUID.
    """
    return f"abandonment-task-{cart_uuid}"


class CartUseCase:
    """
    Centralized use case for handling cart actions.
    """

    def __init__(self, account: str):
        self.account = account
        self.project = self._get_project_by_account()
        self.integrated_feature = self._get_integrated_feature()

    def _get_project_by_account(self) -> Project:
        """
        Fetch the project associated with the account.

        Raises:
            NotFound: If the project is not found.

        Returns:
            Project: The associated project instance.
        """
        try:
            return Project.objects.get(vtex_account=self.account)
        except Project.DoesNotExist:
            error_message = f"Project with account '{self.account}' does not exist."
            logger.error(error_message)
            raise NotFound(error_message)
        except Project.MultipleObjectsReturned:
            error_message = f"Multiple projects found with account '{self.account}'."
            logger.error(error_message)
            raise ValidationError(error_message)

    def _get_integrated_feature(self) -> IntegratedFeature:
        """
        Retrieve the IntegratedFeature for the abandoned cart notification feature
        associated with the current project.

        This method fetches the `IntegratedFeature` associated with the abandoned cart
        functionality for the project linked to this use case.

        Raises:
            NotFound: If the feature or the integration is not found for the project.
            ValidationError: For any other unexpected errors.

        Returns:
            IntegratedFeature: The integrated feature instance for the abandoned cart.
        """
        try:
            feature = Feature.objects.get(
                can_vtex_integrate=True, code="abandoned_cart"
            )
            return IntegratedFeature.objects.get(project=self.project, feature=feature)
        except Feature.DoesNotExist:
            error_message = f"Feature with code 'abandoned_cart' not found."
            logger.error(error_message, exc_info=True)
            raise NotFound(error_message)
        except IntegratedFeature.DoesNotExist:
            error_message = f"IntegratedFeature for project '{self.project}' and feature '{feature}' not found."
            logger.error(error_message, exc_info=True)
            raise NotFound(error_message)
        except Exception as e:
            error_message = (
                f"An unexpected error occurred while retrieving the feature: {str(e)}"
            )
            logger.error(error_message, exc_info=True)
            raise ValidationError(error_message)

    def process_cart_notification(
        self, order_form_id: str, phone: str, name: str
    ) -> Cart:
        """
        Process incoming cart notification, renewing task or creating new cart.

        Args:
            order_form_id (str): The unique identifier for the cart.

        Returns:
            Cart: The created or updated cart instance.
        """
        try:
            # Check if the cart already exists
            cart = Cart.objects.get(
                order_form_id=order_form_id,
                project=self.project,
                phone_number=phone,
                status="created",
            )
            # Renew abandonment task
            self._schedule_abandonment_task(str(cart.uuid))
            return cart
        except Cart.DoesNotExist:
            # Create new cart if it doesn't exist
            return self._create_cart(order_form_id, phone, name)

    def _create_cart(self, order_form_id: str, phone: str, name: str) -> Cart:
        """
        Create a new cart entry and schedule an abandonment task.

        Args:
            order_form_id (str): The UUID of the cart.

        Returns:
            Cart: The created cart instance.
        """
        # Check if templates are synchronized before proceeding
        sync_status = self.integrated_feature.config.get(
            "templates_synchronization_status", "pending"
        )

        if sync_status != "synchronized":
            logger.info(
                f"Templates are not ready (status: {sync_status}) for project {self.project.uuid}. "
                f"Skipping cart creation for order form {order_form_id}."
            )
            raise ValidationError(
                {"error": "Templates are not synchronized"},
                code="templates_not_synchronized",
            )

        cart = Cart.objects.create(
            order_form_id=order_form_id,
            status="created",
            project=self.project,
            integrated_feature=self.integrated_feature,
            phone_number=phone,
            config={"client_name": name},
        )

        # Schedule abandonment task
        self._schedule_abandonment_task(str(cart.uuid))
        return cart

    def _schedule_abandonment_task(self, cart_uuid: str):
        """
        Schedule a task to mark a cart as abandoned after 25 minutes.

        Args:
            cart_uuid (str): The UUID of the cart.
        """
        task_key = generate_task_key(cart_uuid)

        time_restriction_service = CartTimeRestrictionService(self.integrated_feature)
        countdown = time_restriction_service.get_countdown()

        mark_cart_as_abandoned.apply_async(
            (cart_uuid,), countdown=countdown, task_id=task_key
        )
