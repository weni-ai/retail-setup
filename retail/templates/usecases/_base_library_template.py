from typing import TypedDict, Optional, List, Dict, Any

from uuid import UUID

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.templates.tasks import task_create_library_template


class LibraryTemplateData(TypedDict):
    template_name: str
    library_template_name: str
    category: str
    language: str
    app_uuid: str
    project_uuid: str
    start_condition: str
    library_template_button_inputs: Optional[List[Dict[str, Any]]] = None
    integrated_agent: Optional[IntegratedAgent] = None


class BaseLibraryTemplateUseCase:
    def notify_integrations(
        self, version_name: str, version_uuid: UUID, payload: LibraryTemplateData
    ) -> None:
        if (
            not version_name
            or not payload.get("app_uuid")
            or not payload.get("project_uuid")
            or not version_uuid
        ):
            raise ValueError("Missing required data to notify integrations")

        task_create_library_template.delay(
            name=version_name,
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
            category=payload["category"],
            language=payload["language"],
            library_template_name=payload["library_template_name"],
            gallery_version=str(version_uuid),
            library_template_button_inputs=payload.get(
                "library_template_button_inputs"
            ),
        )
