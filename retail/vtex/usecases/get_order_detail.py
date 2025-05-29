from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.base import BaseVtexUseCase


class GetOrderDetailsUsecase(BaseVtexUseCase):
    """
    Use case for retrieving details of a specific order from VTEX IO.
    """

    def __init__(self, vtex_io_service: VtexIOService):
        """
        Initialize the GetOrderDetailsUsecase.

        Args:
            vtex_io_service (VtexIOService): Service for VTEX IO operations.
        """
        self.vtex_io_service = vtex_io_service

    def execute(self, order_id: str, project_uuid: str) -> dict:
        """
        Execute the use case to get order details.

        Args:
            order_id (str): The ID of the order to retrieve.

        Returns:
            dict: Order details from VTEX IO.

        Raises:
            ValueError: If order_id is invalid or order not found.
        """
        if not order_id or not order_id.strip():
            raise ValueError("Order ID is required")

        try:
            return self.vtex_io_service.get_order_details_by_id(
                account_domain=self._get_account_domain(project_uuid), order_id=order_id
            )
        except Exception as e:
            raise ValueError(f"Error fetching order details: {str(e)}")
