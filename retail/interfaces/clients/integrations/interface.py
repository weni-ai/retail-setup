from abc import ABC, abstractmethod

from typing import Optional, Dict, Any


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
