"""
Use case for fetching country phone code from VTEX tenant API.
"""

import logging
from typing import Optional

from retail.agents.shared.country_code_utils import get_phone_code_from_locale
from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService

logger = logging.getLogger(__name__)


class FetchCountryPhoneCodeUseCase:
    """
    Use case responsible for fetching the country phone code from VTEX.

    This use case:
    1. Calls VTEX proxy to get tenant info
    2. Extracts defaultLocale from response
    3. Converts locale to phone code using phonenumbers

    Can be easily mocked in tests by injecting a mock VtexIOService.
    """

    def __init__(self, vtex_io_service: Optional[VtexIOService] = None):
        self.vtex_io_service = vtex_io_service or VtexIOService()

    def execute(self, project: Project) -> Optional[str]:
        """
        Fetch country phone code for a project.

        Args:
            project: Project with vtex_account configured.

        Returns:
            Phone code string (e.g., '55') or None if failed.
        """
        vtex_account = project.vtex_account
        if not vtex_account:
            logger.warning(
                f"[FetchCountryPhoneCode] No vtex_account: project={project.uuid}"
            )
            return None

        account_domain = f"{vtex_account}.myvtex.com"
        project_uuid = str(project.uuid)

        try:
            logger.info(
                f"[FetchCountryPhoneCode] Fetching tenant: "
                f"project={project_uuid} vtex_account={vtex_account}"
            )

            response = self.vtex_io_service.proxy_vtex(
                account_domain=account_domain,
                project_uuid=project_uuid,
                method="GET",
                path=f"/api/tenant/tenants?q={vtex_account}",
            )

            locale = self._extract_locale(response)
            if not locale:
                logger.warning(
                    f"[FetchCountryPhoneCode] No locale found: project={project_uuid}"
                )
                return None

            phone_code = get_phone_code_from_locale(locale)

            logger.info(
                f"[FetchCountryPhoneCode] Success: project={project_uuid} "
                f"locale={locale} phone_code={phone_code}"
            )

            return phone_code

        except Exception as e:
            logger.error(
                f"[FetchCountryPhoneCode] Failed: project={project_uuid} error={e}"
            )
            return None

    def _extract_locale(self, response) -> Optional[str]:
        """Extract defaultLocale from VTEX tenant API response."""
        if not response:
            return None

        # Handle both single object and array response
        tenant_data = response if isinstance(response, dict) else None
        if isinstance(response, list) and len(response) > 0:
            tenant_data = response[0]

        if not tenant_data:
            return None

        return tenant_data.get("defaultLocale", "")
