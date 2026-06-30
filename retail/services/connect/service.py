import logging

from typing import Dict, List, Optional

from retail.interfaces.clients.connect.interface import ConnectClientInterface
from retail.interfaces.services.connect import ConnectServiceInterface
from retail.clients.connect.client import ConnectClient


logger = logging.getLogger(__name__)


class ConnectService(ConnectServiceInterface):
    def __init__(self, connect_client: Optional[ConnectClientInterface] = None):
        self.connect_client = connect_client or ConnectClient()

    def get_user_permissions(
        self, project_uuid, user_email, user_token: Optional[str] = None
    ):
        return self.connect_client.get_user_permissions(
            project_uuid, user_email, user_token
        )

    def create_vtex_project(
        self,
        user_email: str,
        vtex_account: str,
        language: str,
        organization_name: str,
        project_name: str,
    ) -> Dict:
        return self.connect_client.create_vtex_project(
            user_email=user_email,
            vtex_account=vtex_account,
            language=language,
            organization_name=organization_name,
            project_name=project_name,
        )

    def link_vtex_account(self, project_uuid: str, vtex_account: str) -> Dict:
        return self.connect_client.link_vtex_account(
            project_uuid=project_uuid,
            vtex_account=vtex_account,
        )

    def send_data_export_email(
        self,
        user_email: str,
        file_url: str,
        start_date: str,
        end_date: str,
        template: str,
        status: List[str],
    ) -> Optional[Dict]:
        try:
            return self.connect_client.send_data_export_email(
                user_email=user_email,
                file_url=file_url,
                start_date=start_date,
                end_date=end_date,
                template=template,
                status=status,
            )
        except Exception as exc:
            logger.error(f"Failed to send data export email to {user_email}: {exc}")
            return None

    def send_contract_acceptance_email(
        self,
        user_email: str,
        acceptance_id: str,
        subject: str,
        body_html: str,
        file_name: str,
        file_base64: str,
    ) -> Optional[Dict]:
        try:
            return self.connect_client.send_contract_acceptance_email(
                user_email=user_email,
                acceptance_id=acceptance_id,
                subject=subject,
                body_html=body_html,
                file_name=file_name,
                file_base64=file_base64,
            )
        except Exception as exc:
            logger.error(
                f"Failed to send contract acceptance email to {user_email}: {exc}"
            )
            return None

    def update_project_config(
        self,
        project_uuid: str,
        config: Dict,
    ) -> Dict:
        return self.connect_client.update_project_config(
            project_uuid=project_uuid,
            config=config,
        )

    def get_project_plan_status(self, project_uuid: str) -> Dict:
        return self.connect_client.get_project_plan_status(
            project_uuid=project_uuid,
        )
