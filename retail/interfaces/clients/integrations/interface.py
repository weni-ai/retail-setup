from abc import ABC, abstractmethod


class IntegrationsClientInterface(ABC):
    @abstractmethod
    def get_vtex_integration_detail(self, project_uuid: str):
        pass

    @abstractmethod
    def create_template_message(
        self, app_uuid: str, project_uuid: str, name: str, category: str
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
