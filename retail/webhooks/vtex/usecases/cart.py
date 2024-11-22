from rest_framework.exceptions import ValidationError, NotFound
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.webhooks.vtex.dtos.cart_dto import CartDTO


class CartUseCase:
    """
    Centralized use case for handling cart actions.
    """

    def __init__(self, account: str):
        self.account = account
        self.project = self._get_project_by_account()

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
        Ensure that a user has only one cart with the status "created".

        Args:
            home_phone (str): The user's phone number.

        Raises:
            ValidationError: If a cart with the "created" status already exists.
        """
        # Check if there's an existing cart with the status "created"
        cart_exists = Cart.objects.filter(
            phone_number=home_phone, project=self.project, status="created"
        ).exists()

        if cart_exists:
            raise ValidationError(
                {"cart": f"User with phone '{home_phone}' already has an active cart."}
            )

    def _create_cart(self, dto: CartDTO) -> Cart:
        """
        Create a new cart entry.

        Args:
            dto (CartDTO): The cart DTO.

        Returns:
            Cart: The created cart instance.
        """
        self._ensure_single_cart(dto.home_phone)

        return Cart.objects.create(
            phone_number=dto.home_phone,
            config=dto.data,
            status="created",
            project=self.project,
        )

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
            cart.save()
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
            cart.save()
            return cart
        except Cart.DoesNotExist:
            raise NotFound(f"Cart for phone '{dto.home_phone}' does not exist.")
