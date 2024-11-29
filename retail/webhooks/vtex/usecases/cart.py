import logging

from django.conf import settings

from rest_framework.exceptions import ValidationError, NotFound
from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.vtex.tasks import mark_cart_as_abandoned
from retail.vtex.usecases.phone_number_normalizer import PhoneNumberNormalizer
from retail.webhooks.vtex.dtos.cart_dto import CartDTO

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

    def handle_action(self, action: str, cart_dto: CartDTO) -> Cart:
        """
        Handle the specified cart action.

        Args:
            action (str): The action to handle (create, update, purchased, empty).
            cart_dto (CartDTO): The validated cart data.

        Returns:
            Cart: The updated or created cart instance.
        """
        action_methods = {
            "create": self._create_cart,
            "update": self._update_cart,
            "purchased": self._mark_cart_purchased,
            "empty": self._mark_cart_empty,
        }

        if action not in action_methods:
            raise ValidationError({"action": f"Invalid action: {action}"})

        # Call the appropriate method dynamically
        return action_methods[action](cart_dto)

    def _ensure_single_cart(self, home_phone: str):
        """
        Ensure that a user has only one cart with the status "created" and not abandoned.

        Args:
            home_phone (str): The user's phone number.

        Raises:
            ValidationError: If a cart with the "created" status already exists.
        """
        cart_exists = Cart.objects.filter(
            phone_number=home_phone,
            project=self.project,
            status="created",
            abandoned=False,
        ).exists()

        if cart_exists:
            raise ValidationError(
                {"cart": f"User with phone '{home_phone}' already has an active cart."}
            )

    def _schedule_abandonment_task(self, cart_uuid: str):
        """
        Schedule a task to mark a cart as abandoned after 25 minutes.

        Args:
            cart_uuid (str): The UUID of the cart.

        Returns:
            AsyncResult: The result object for the scheduled task.
        """
        task_key = generate_task_key(cart_uuid)

        # Schedule the task and capture the AsyncResult
        mark_cart_as_abandoned.apply_async(
            (cart_uuid,), countdown=25 * 60, task_id=task_key
        )

        # Log task details for debugging
        print(f"Scheduled task with ID: {task_key}")

    def _cancel_abandonment_task(self, cart_uuid: str):
        """
        Cancel a previously scheduled abandonment task.

        Args:
            cart_uuid (str): The UUID of the cart.
        """
        task_key = generate_task_key(cart_uuid)
        celery_app.control.revoke(task_key, terminate=True)

    def _create_cart(self, dto: CartDTO) -> Cart:
        """
        Create a new cart entry.

        Args:
            dto (CartDTO): The cart DTO.

        Returns:
            Cart: The created cart instance.
        """
        self._ensure_single_cart(dto.home_phone)

        try:
            normalized_phone = PhoneNumberNormalizer.normalize(dto.home_phone)
        except ValueError as e:
            raise ValidationError({"phone_number": str(e)})

        integrated_feature = self._get_feature()
        cart = Cart.objects.create(
            phone_number=normalized_phone,
            config=dto.data,
            status="created",
            project=self.project,
            integrated_feature=integrated_feature,
        )

        # Schedule abandonment task
        self._schedule_abandonment_task(str(cart.uuid))
        return cart

    def _update_cart(self, dto: CartDTO) -> Cart:
        """
        Update an existing cart.

        Args:
            dto (CartDTO): The cart DTO.

        Returns:
            Cart: The updated cart instance.
        """
        try:
            cart = Cart.objects.filter(
                phone_number=dto.home_phone, project=self.project
            ).latest("created_on")

            cart.config.update(dto.data)
            cart.save()

            # Reschedule abandonment task
            self._schedule_abandonment_task(str(cart.uuid))
            return cart
        except Cart.DoesNotExist:
            raise NotFound(f"Cart for phone '{dto.home_phone}' does not exist.")

    def _mark_cart_purchased(self, dto: CartDTO) -> Cart:
        """
        Mark a cart as purchased.

        Args:
            dto (CartDTO): The cart DTO.

        Returns:
            Cart: The updated cart instance.
        """
        try:
            cart = Cart.objects.filter(
                phone_number=dto.home_phone, project=self.project
            ).latest("created_on")

            cart.status = "purchased"
            cart.abandoned = False
            cart.save()

            # Cancel abandonment task
            self._cancel_abandonment_task(str(cart.uuid))
            return cart
        except Cart.DoesNotExist:
            raise NotFound(f"Cart for phone '{dto.home_phone}' does not exist.")

    def _mark_cart_empty(self, dto: CartDTO) -> Cart:
        """
        Mark a cart as empty.

        Args:
            dto (CartDTO): The cart DTO.

        Returns:
            Cart: The updated cart instance.
        """
        try:
            cart = Cart.objects.filter(
                phone_number=dto.home_phone, project=self.project
            ).latest("created_on")

            cart.status = "empty"
            cart.abandoned = False
            cart.save()

            # Cancel abandonment task
            self._cancel_abandonment_task(str(cart.uuid))
            return cart
        except Cart.DoesNotExist:
            raise NotFound(f"Cart for phone '{dto.home_phone}' does not exist.")
