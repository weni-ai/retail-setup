from typing import TypedDict, List, Dict, Any

from rest_framework.exceptions import NotFound

from retail.templates.models import Template, Version

from ._base_library_template import LibraryTemplateData, BaseLibraryTemplateUseCase


class UpdateLibraryTemplateData(TypedDict):
    template_uuid: str
    app_uuid: str
    project_uuid: str
    library_template_button_inputs: List[Dict[str, Any]]


class UpdateLibraryTemplateUseCase(BaseLibraryTemplateUseCase):
    def _get_template(self, template_uuid: str) -> Template:
        try:
            return Template.objects.get(uuid=template_uuid)
        except Template.DoesNotExist:
            raise NotFound(f"Template not found: {template_uuid}")

    def _update_template_metadata(
        self, template: Template, payload: LibraryTemplateData
    ) -> None:
        if payload.get("library_template_button_inputs"):
            metadata = template.metadata or {}
            updated_buttons = []

            for button_input in payload["library_template_button_inputs"]:
                button = {
                    "type": button_input.get("type", "URL"),
                    "text": button_input.get("text", "Ver detalhes"),
                }

                url_data = button_input["url"]

                button["url"] = url_data["base_url"]

                if "url_suffix_example" in url_data:
                    button["example"] = [url_data["url_suffix_example"]]

                updated_buttons.append(button)

            metadata["buttons"] = updated_buttons
            template.metadata = metadata
            template.save()

    def _build_payload(
        self, template: Template, payload: UpdateLibraryTemplateData
    ) -> LibraryTemplateData:
        return {
            "library_template_name": template.name,
            "category": template.metadata.get("category"),
            "language": template.metadata.get("language"),
            "app_uuid": payload.get("app_uuid"),
            "project_uuid": payload.get("project_uuid"),
            "library_template_button_inputs": payload.get(
                "library_template_button_inputs"
            ),
        }

    def _get_last_version(self, template: Template) -> Version:
        return template.versions.order_by("-id").first()

    def execute(self, payload: UpdateLibraryTemplateData) -> None:
        template = self._get_template(payload["template_uuid"])
        template.needs_button_edit = False
        version = self._get_last_version(template)
        payload = self._build_payload(template, payload)
        self._update_template_metadata(template, payload)
        self.notify_integrations(version.template_name, version.uuid, payload)
        return template
