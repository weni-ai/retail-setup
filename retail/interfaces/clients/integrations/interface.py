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
    def fetch_templates_from_user(
        self,
        app_uuid: str,
        project_uuid: str,
        template_names: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def create_wwc_app(self, project_uuid: str, config: Dict) -> Dict:
        """
        Creates a WWC (Weni Web Chat) app for the given project.

        Args:
            project_uuid: The project's unique identifier.
            config: Initial app configuration payload.

        Returns:
            Dict containing the created app data (uuid, config, etc.).
        """
        pass

    @abstractmethod
    def configure_wwc_app(self, app_uuid: str, config: Dict) -> Dict:
        """
        Configures a previously created WWC app.

        Args:
            app_uuid: The WWC app's unique identifier.
            config: The channel configuration payload.

        Returns:
            Dict containing the configured app data (uuid, script URL).
        """
        pass
