import base64

import string

import binascii

from typing import Dict, Optional, List, Protocol


class ComponentTransformer(Protocol):
    """Protocol for component transformers."""

    def transform(self, template_data: Dict) -> Optional[Dict]:
        """Transform component data from library format to translation format."""
        ...


class HeaderTransformer(ComponentTransformer):
    """Transforms header component from library to translation format."""

    def _is_base_64(self, header: str) -> bool:
        HEURISTIC_MIN_LENGTH = 100

        if header.startswith("data:"):
            header = header.split(",", 1)[1]

        if len(header) < HEURISTIC_MIN_LENGTH:
            return False

        base64_charset = set(string.ascii_letters + string.digits + "+/=")
        if any(c not in base64_charset for c in header):
            return False

        try:
            base64.b64decode(header, validate=True)
            return True
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return False

    def _is_header_format_already_translated(self, header) -> bool:
        return isinstance(header, dict) and "header_type" in header and "text" in header

    def transform(self, template_data: Dict) -> Optional[Dict]:
        if not template_data.get("header"):
            return None

        if self._is_header_format_already_translated(template_data["header"]):
            return template_data["header"]

        if self._is_base_64(template_data["header"]):
            return {"header_type": "IMAGE", "text": template_data["header"]}

        return {"header_type": "TEXT", "text": template_data["header"]}


class BodyTransformer(ComponentTransformer):
    """Transforms body component from library to translation format."""

    def transform(self, template_data: Dict) -> Optional[Dict]:
        if not template_data.get("body"):
            return None

        body_data = {"type": "BODY", "text": template_data["body"]}

        if template_data.get("body_params"):
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
        self.header_transformer = header_transformer or HeaderTransformer()
        self.body_transformer = body_transformer or BodyTransformer()
        self.footer_transformer = footer_transformer or FooterTransformer()
        self.button_transformer = button_transformer or ButtonTransformer()

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

        header_data = self.header_transformer.transform(template_data)
        body_data = self.body_transformer.transform(template_data)
        footer_data = self.footer_transformer.transform(template_data)
        buttons_data = self.button_transformer.transform(template_data)

        translation_payload = {
            "language": language,
        }

        if header_data:
            translation_payload["header"] = header_data
        if footer_data:
            translation_payload["footer"] = footer_data
        if buttons_data:
            translation_payload["buttons"] = buttons_data
        if body_data:
            translation_payload["body"] = body_data

        return translation_payload
