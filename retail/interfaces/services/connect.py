from typing import Protocol, Tuple, Dict, List, Optional


class ConnectServiceInterface(Protocol):
    def get_user_permissions(
        self, project_uuid: str, user_email: str, user_token: Optional[str] = None
    ) -> Tuple[int, Dict[str, str]]:
        ...

    def create_vtex_project(
        self,
        user_email: str,
        vtex_account: str,
        language: str,
        organization_name: str,
        project_name: str,
    ) -> Dict:
        ...

    def send_data_export_email(
        self,
        user_email: str,
        file_url: str,
        start_date: str,
        end_date: str,
        template: str,
        status: List[str],
    ) -> Optional[Dict]:
        ...

    def update_project_config(
        self,
        project_uuid: str,
        config: Dict,
    ) -> Dict:
        ...

    def get_project_plan_status(self, project_uuid: str) -> Dict:
        ...
