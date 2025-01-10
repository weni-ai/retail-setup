import logging

from django.conf import settings

from rest_framework.exceptions import ValidationError, NotFound
from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.vtex.tasks import mark_cart_as_abandoned

from retail.celery import app as celery_app


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
        self.feature = self._get_feature()

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
            raise NotFound(f"Project with account '{self.account}' does not exist.")

    def _get_feature(self) -> IntegratedFeature:
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
            abandoned_cart_feature_uuid = settings.ABANDONED_CART_FEATURE_UUID
            feature = Feature.objects.get(uuid=abandoned_cart_feature_uuid)
            return IntegratedFeature.objects.get(project=self.project, feature=feature)
        except Feature.DoesNotExist:
            error_message = (
                f"Feature with UUID {abandoned_cart_feature_uuid} not found."
            )
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
            logger.error(error_message, exc_info=True)  # Captura o traceback completo
            raise ValidationError(error_message)

    def process_cart_notification(self, cart_id: str, phone: str) -> Cart:
        """
        Process incoming cart notification, renewing task or creating new cart.

        Args:
            cart_id (str): The unique identifier for the cart.

        Returns:
            Cart: The created or updated cart instance.
        """
        try:
            # Check if the cart already exists
            cart = Cart.objects.get(
                cart_id=cart_id,
                project=self.project,
                phone_number=phone,
                status="created",
            )
            # Renew abandonment task
            self._schedule_abandonment_task(str(cart.uuid))
            return cart
        except Cart.DoesNotExist:
            # Create new cart if it doesn't exist
            return self._create_cart(cart_id, phone)

    def _create_cart(self, cart_id: str, phone: str) -> Cart:
        """
        Create a new cart entry and schedule an abandonment task.

        Args:
            cart_id (str): The UUID of the cart.

        Returns:
            Cart: The created cart instance.
        """
        cart = Cart.objects.create(
            cart_id=cart_id,
            status="created",
            project=self.project,
            integrated_feature=self._get_feature(),
            phone_number=phone,
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

        mark_cart_as_abandoned.apply_async(
            (cart_uuid,), countdown=25 * 60, task_id=task_key
        )
