"""
Use case for registering (or attaching) a WhatsApp click-ID to a VTEX
order-form stored in the Cart model.
"""

from typing import Optional, TYPE_CHECKING

from retail.vtex.dtos.register_order_form_dto import RegisterOrderFormDTO
from retail.vtex.repositories.cart_repository import CartRepository
from retail.projects.models import Project

from rest_framework.exceptions import ValidationError


if TYPE_CHECKING:  # only for static type checking
    from ..models import Cart


class RegisterOrderFormClickUseCase:
    """Link a WhatsApp click-ID to the corresponding cart."""

    def __init__(
        self,
        project_uuid: str,
        repository: Optional[CartRepository] = None,
    ) -> None:
        """
        Initialize the use case.

        Args:
            project_uuid: The UUID of the project.
            repository: Concrete implementation responsible for persistence.
        """
        self._repo: CartRepository = repository or CartRepository()
        self._project_uuid = project_uuid

    def execute(self, dto: RegisterOrderFormDTO) -> "Cart":
        """
        Perform the registration and return the affected cart.

        The operation is idempotent.

        Args:
            dto: Immutable data required by the use case.

        Returns:
            The persisted :class:`Cart` instance.

        Raises:
            ValidationError: If the click-ID is already linked to another cart.
            ValidationError: If the project does not exist.
        """
        project = self._validate_project_exists()

        cart = self._repo.find_by_order_form(dto.order_form_id, project)
        if cart is None:
            cart = self._repo.create(
                order_form_id=dto.order_form_id,
                project=project,
                flows_channel_uuid=dto.channel_uuid,
            )

        return cart

    def _validate_project_exists(self) -> Project:
        """
        Validate if the project exists and is unique.

        Raises:
            ValidationError: If the project does not exist or if there are duplicate projects.
        """
        try:
            return Project.objects.get(uuid=self._project_uuid)
        except Project.DoesNotExist:
            raise ValidationError(
                f"Project with UUID '{self._project_uuid}' not found."
            )
        except Project.MultipleObjectsReturned:
            raise ValidationError(
                f"Duplicate projects found with UUID '{self._project_uuid}'."
            )
