import base64

from typing import Dict, Optional, List, Protocol


class ComponentTransformer(Protocol):
    """Protocol for component transformers."""

    def transform(self, template_data: Dict) -> Optional[Dict]:
        """Transform component data from library format to translation format."""
        ...


class HeaderTransformer(ComponentTransformer):
    """Transforms header component from library to translation format."""

    def _is_base_64(self, header: str) -> bool:
        try:
            b = header.encode("utf-8")
            base64.b64decode(b, validate=True)
            return True
        except Exception:
            return False

    def transform(self, template_data: Dict) -> Optional[Dict]:
        if not template_data.get("header"):
            return None

        if self._is_base_64(template_data["header"]):
            return {"header_type": "IMAGE", "example": template_data["header"]}

        return {"header_type": "TEXT", "text": template_data["header"]}


class BodyTransformer(ComponentTransformer):
    """Transforms body component from library to translation format."""

    def transform(self, template_data: Dict) -> Dict:
        body_data = {"type": "BODY", "text": template_data["body"]}

        if "body_params" in template_data:
            body_data["example"] = {"body_text": [template_data["body_params"]]}

        return body_data


class FooterTransformer(ComponentTransformer):
    """Transforms footer component from library to translation format."""

    def transform(self, template_data: Dict) -> Optional[Dict]:
        if not template_data.get("footer"):
            return None
        return {"type": "FOOTER", "text": template_data["footer"]}


class ButtonTransformer(ComponentTransformer):
    """Transforms buttons component from library to translation format."""

    def _is_button_format_already_translated(self, button: Dict) -> bool:
        return button.get("type") == "URL" and isinstance(button.get("url"), str)

    def transform(self, template_data: Dict) -> Optional[List[Dict]]:
        buttons = template_data.get("buttons")

        if buttons is None:
            return None

        buttons_data = []

        for btn in buttons:
            if self._is_button_format_already_translated(btn):
                continue

            button = {"type": btn["type"], "text": btn["text"]}

            if btn["type"] == "URL":
                if "url_suffix_example" in btn["url"]:
                    button["example"] = [btn["url"]["url_suffix_example"]]
                    button["url"] = btn["url"]["base_url"] + "{{1}}"
                else:
                    button["url"] = btn["url"]["base_url"]

            elif btn["type"] == "PHONE_NUMBER":
                button["phone_number"] = btn["phone_number"]
                button["country_code"] = btn.get("country_code", "55")

            buttons_data.append(button)

        return buttons_data


class TemplateTranslationAdapter:
    """
    Adapter responsible for transforming library template metadata
    to translation format using component transformers.
    """

    def __init__(
        self,
        header_transformer: Optional[ComponentTransformer] = None,
        body_transformer: Optional[ComponentTransformer] = None,
        footer_transformer: Optional[ComponentTransformer] = None,
        button_transformer: Optional[ComponentTransformer] = None,
    ):
        self._header_transformer = header_transformer or HeaderTransformer()
        self._body_transformer = body_transformer or BodyTransformer()
        self._footer_transformer = footer_transformer or FooterTransformer()
        self._button_transformer = button_transformer or ButtonTransformer()

    def adapt(self, template_data: Dict) -> Dict:
        """
        Adapts a message_template_library (pre-approved) template metadata to the format
        required for template translation creation in the integrations module.

        Args:
            template_data (dict): The original metadata from the template.

        Returns:
            dict: translation_payload formatted for integrations.
        """
        language = template_data.get("language", "pt_BR")

        header_data = self._header_transformer.transform(template_data)
        body_data = self._body_transformer.transform(template_data)
        footer_data = self._footer_transformer.transform(template_data)
        buttons_data = self._button_transformer.transform(template_data)

        translation_payload = {
            "language": language,
            "body": body_data,
        }

        if header_data:
            translation_payload["header"] = header_data
        if footer_data:
            translation_payload["footer"] = footer_data
        if buttons_data:
            translation_payload["buttons"] = buttons_data

        return translation_payload
