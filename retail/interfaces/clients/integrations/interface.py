from abc import ABC, abstractmethod

from typing import List, Optional, Dict, Any


class IntegrationsClientInterface(ABC):
    @abstractmethod
    def get_vtex_integration_detail(self, project_uuid: str):
        pass

    @abstractmethod
    def create_template_message(
        self,
        app_uuid: str,
        project_uuid: str,
        name: str,
        category: str,
        gallery_version: Optional[str] = None,
    ) -> str:
        pass

    @abstractmethod
    def create_template_translation(
        self, app_uuid: str, project_uuid: str, template_uuid: str, payload: dict
    ) -> dict:
        pass

    @abstractmethod
    def create_library_template_message(
        self, app_uuid: str, project_uuid: str, template_data: str
    ) -> str:
        pass

    @abstractmethod
    def get_synchronized_templates(self, app_uuid: str, template_list: list) -> str:
        pass

    @abstractmethod
    def create_library_template(
        self, app_uuid: str, project_uuid: str, template_data: Dict[str, Any]
    ) -> str:
        pass

    @abstractmethod
    def fetch_template_metrics(
        self, app_uuid: str, template_versions: List[str], start: str, end: str
    ) -> Dict:
        pass

    @abstractmethod
    def fetch_templates_from_user(self, app_uuid: str) -> List[Dict[str, Any]]:
        pass
