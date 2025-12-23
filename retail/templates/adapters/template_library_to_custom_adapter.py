import base64

import string

import binascii

from typing import Dict, Optional, List, Protocol, Union


class ComponentTransformer(Protocol):
    """Protocol for component transformers."""

    def transform(self, template_data: Dict) -> Optional[Union[Dict, List[Dict]]]:
        """Transform component data from library format to translation format."""
        ...


class HeaderTransformer(ComponentTransformer):
    """Transforms header component from library to translation format."""

    IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

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

    def _is_image_url(self, header: str) -> bool:
        """Check if header is a URL pointing to an image file."""
        if not header.startswith(("http://", "https://")):
            return False
        # Remove query string to check file extension
        url_without_query = header.split("?")[0]
        return url_without_query.lower().endswith(self.IMAGE_EXTENSIONS)

    def _is_header_format_already_translated(self, header) -> bool:
        return isinstance(header, dict) and "header_type" in header and "text" in header

    def transform(self, template_data: Dict) -> Optional[Dict]:
        if not template_data.get("header"):
            return None

        header = template_data["header"]

        if self._is_header_format_already_translated(header):
            return header

        if self._is_base_64(header):
            return {"header_type": "IMAGE", "text": header}

        if self._is_image_url(header):
            return {"header_type": "IMAGE", "text": header}

        return {"header_type": "TEXT", "text": header}


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

    PLACEHOLDER_PATTERN = "{{1}}"

    def _is_button_format_already_translated(self, button: Dict) -> bool:
        return button.get("type") == "URL" and isinstance(button.get("url"), str)

    def _looks_like_url(self, value: str) -> bool:
        """Check if value looks like a URL (contains domain pattern)."""
        if not value:
            return False
        # Already has protocol
        if value.startswith(("http://", "https://")):
            return True
        # Contains domain pattern (has a dot and slash indicating path)
        return "." in value and "/" in value

    def _ensure_protocol(self, url: str) -> str:
        """Add https:// protocol prefix if not already present."""
        if not url:
            return url
        if not url.startswith(("http://", "https://")):
            return f"https://{url}"
        return url

    def _normalize_url_if_needed(self, value: str) -> str:
        """Normalize URL only if it looks like a complete URL."""
        if self._looks_like_url(value):
            return self._ensure_protocol(value)
        return value

    def _append_placeholder_if_needed(self, url: str) -> str:
        """Append placeholder {{1}} only if not already present in URL."""
        if self.PLACEHOLDER_PATTERN in url:
            return url
        return url + self.PLACEHOLDER_PATTERN

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
                base_url = self._ensure_protocol(btn["url"]["base_url"])
                if "url_suffix_example" in btn["url"]:
                    button["example"] = [
                        self._normalize_url_if_needed(btn["url"]["url_suffix_example"])
                    ]
                    button["url"] = self._append_placeholder_if_needed(base_url)
                else:
                    button["url"] = base_url

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
