from typing import Dict, List, Optional
from django.conf import settings

from retail.interfaces.clients.connect.interface import (
    ConnectClientInterface,
)
from retail.clients.base import (
    RequestClient,
    InternalAuthentication,
    UserAuthentication,
)


class ConnectClient(RequestClient, ConnectClientInterface):
    def __init__(self):
        self.base_url = settings.CONNECT_REST_ENDPOINT
        self.internal_authentication = InternalAuthentication()

    def get_user_permissions(
        self, project_uuid, user_email, user_token: Optional[str] = None
    ):
        url = f"{self.base_url}/v2/projects/{project_uuid}/authorization"

        if user_token:
            auth_instance = UserAuthentication(user_token)
            params = {}
        else:
            auth_instance = self.internal_authentication
            params = {"user": user_email}

        response = self.make_request(
            url=url,
            method="GET",
            headers=auth_instance.headers,
            params=params,
        )

        return response.status_code, response.json()

    def create_vtex_project(
        self,
        user_email: str,
        vtex_account: str,
        language: str,
        organization_name: str,
        project_name: str,
    ) -> Dict:
        url = f"{self.base_url}/v2/commerce/create-vtex-project/"

        payload: Dict = {
            "user_email": user_email,
            "vtex_account": vtex_account,
            "language": language,
            "organization_name": organization_name,
            "project_name": project_name,
        }

        response = self.make_request(
            url=url,
            method="POST",
            json=payload,
            headers=self.internal_authentication.headers,
        )
        return response.json()

    def send_data_export_email(
        self,
        user_email: str,
        file_url: str,
        start_date: str,
        end_date: str,
        template: str,
        status: List[str],
    ) -> Dict:
        url = f"{self.base_url}/v2/commerce/send-data-export-email/"

        payload: Dict = {
            "user_email": user_email,
            "file_url": file_url,
            "start_date": start_date,
            "end_date": end_date,
            "template": template,
            "status": status,
        }

        response = self.make_request(
            url=url,
            method="POST",
            json=payload,
            headers=self.internal_authentication.headers,
        )
        return response.json()

    def update_project_config(
        self,
        project_uuid: str,
        config: Dict,
    ) -> Dict:
        url = f"{self.base_url}/v2/commerce/projects/" f"{project_uuid}/config/"

        response = self.make_request(
            url=url,
            method="PATCH",
            json={"config": config},
            headers=self.internal_authentication.headers,
        )
        return response.json()

    def get_project_plan_status(self, project_uuid: str) -> Dict:
        """
        Fetch the billing plan status for a project from Connect.

        The endpoint is service-to-service and requires the
        ``can_communicate_internally`` permission, which is granted via
        the JWT claim used by ``InternalAuthentication``.

        Connect caches the response in Redis for ~15 minutes and
        invalidates it on plan/suspension signals, so this call is safe
        to invoke per request.

        Response payload (7 fields):
            project_uuid (str)
            organization_uuid (str | None)
            plan (str | None) — trial | free | start | scale |
                advanced | enterprise | internal_weni | None
            is_trial (bool) — UI/badge only; do NOT use for gating
            is_trial_active (bool) — single source of truth for gating
                trial-only features. Equivalent to
                ``plan == "trial" AND is_active AND NOT is_suspended``.
            is_active (bool)
            is_suspended (bool)
        """
        url = (
            f"{self.base_url}/v2/internals/connect/projects/"
            f"{project_uuid}/plan-status"
        )

        response = self.make_request(
            url=url,
            method="GET",
            headers=self.internal_authentication.headers,
        )
        return response.json()
