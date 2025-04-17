from retail.services.vtex_io.service import VtexIOService
from retail.projects.models import Project


class GetOrdersUsecase:
    def __init__(self, vtex_io_service: VtexIOService):
        self.vtex_io_service = vtex_io_service

    def _get_account_domain(self, project_uuid: str) -> str:
        """
        Get the VTEX account domain from the project.

        Args:
            project_uuid (str): The UUID of the project

        Returns:
            str: The complete VTEX account domain
        """
        try:
            project = Project.objects.get(uuid=project_uuid)
            return f"{project.vtex_account}.myvtex.com"
        except Project.DoesNotExist:
            # Default fallback or raise an exception based on requirements
            return "wenipartnerbr.myvtex.com"

    def execute(self, data: dict) -> dict:
        """
        Execute the get orders use case.

        Args:
            params (dict): Parameters containing project_uuid and other query parameters

        Returns:
            dict: Orders data from VTEX IO
        """
        # Remove project_uuid from params as it's not needed for the VTEX API call
        project_uuid = data.get("project_uuid")
        raw_query = data.get("raw_query")
        account_domain = self._get_account_domain(project_uuid)
        return self.vtex_io_service.get_orders(
            account_domain=account_domain, query_params=raw_query
        )
