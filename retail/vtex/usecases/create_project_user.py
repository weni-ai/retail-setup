"""
Use case for creating a VTEX project in Connect with locale-aware language.

Fetches the VTEX tenant locale via the IO proxy (standard pattern) and
converts it to the Connect language format before forwarding the request.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from retail.agents.shared.country_code_utils import (
    convert_vtex_locale_to_connect_language,
)
from retail.services.connect.service import ConnectService
from retail.services.vtex_io.service import VtexIOService

logger = logging.getLogger(__name__)


@dataclass
class CreateProjectUserDTO:
    vtex_account: str
    user_email: str


class CreateProjectUserUseCase:
    """
    Creates a project in Connect on behalf of the IO front-end.

    Steps:
        1. Fetch the VTEX tenant locale via the IO proxy.
        2. Convert the locale to Connect's language format.
        3. Call Connect to create the project, forwarding user_email,
           vtex_account and the resolved language.
    """

    def __init__(
        self,
        connect_service: Optional[ConnectService] = None,
        vtex_io_service: Optional[VtexIOService] = None,
    ):
        self.connect_service = connect_service or ConnectService()
        self.vtex_io_service = vtex_io_service or VtexIOService()

    def execute(self, dto: CreateProjectUserDTO) -> Dict:
        locale = self._fetch_vtex_locale(dto.vtex_account)
        language = convert_vtex_locale_to_connect_language(locale)

        logger.info(
            f"[CreateProjectUser] vtex_account={dto.vtex_account} "
            f"locale={locale} language={language}"
        )

        result = self.connect_service.create_vtex_project(
            user_email=dto.user_email,
            vtex_account=dto.vtex_account,
            language=language,
        )

        logger.info(
            f"[CreateProjectUser] Project created: vtex_account={dto.vtex_account} "
            f"project_uuid={result.get('project_uuid')}"
        )
        return result

    def _fetch_vtex_locale(self, vtex_account: str) -> Optional[str]:
        """
        Fetch defaultLocale from the VTEX tenant API via the IO proxy.
        """
        account_domain = f"{vtex_account}.myvtex.com"

        try:
            response = self.vtex_io_service.proxy_vtex(
                account_domain=account_domain,
                vtex_account=vtex_account,
                method="GET",
                path=f"/api/tenant/tenants?q={vtex_account}",
            )

            locale = self._extract_locale(response)
            if locale:
                logger.info(
                    f"[CreateProjectUser] Tenant locale: "
                    f"vtex_account={vtex_account} locale={locale}"
                )
            else:
                logger.warning(
                    f"[CreateProjectUser] No locale found: "
                    f"vtex_account={vtex_account}"
                )
            return locale

        except Exception as e:
            logger.warning(
                f"[CreateProjectUser] Failed to fetch tenant locale: "
                f"vtex_account={vtex_account} error={e}"
            )
            return None

    @staticmethod
    def _extract_locale(response) -> Optional[str]:
        """Extract defaultLocale from VTEX tenant API response."""
        if not response:
            return None

        tenant = response if isinstance(response, dict) else None
        if isinstance(response, list) and len(response) > 0:
            tenant = response[0]

        if not tenant:
            return None

        return tenant.get("defaultLocale", "")
