from typing import Protocol, Dict, Any, Optional, List


class IntegrationsServiceInterface(Protocol):
    def create_template(
        self,
        app_uuid: str,
        project_uuid: str,
        name: str,
        category: str,
        gallery_version: Optional[str] = None,
    ) -> str: ...

    def create_template_translation(
        self,
        app_uuid: str,
        project_uuid: str,
        template_uuid: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]: ...

    def fetch_templates_from_user(
        self, app_uuid: str, templates_names: List[str], language: str
    ) -> Dict[str, Dict[str, Any]]: ...
