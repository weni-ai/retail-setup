import base64
import re
import string

import binascii

from typing import Any, Dict, Optional, List, Protocol, Union

from retail.templates.adapters.url_normalization import (
    append_placeholder_if_needed,
    ensure_protocol,
    normalize_url_if_needed,
)


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


_COMPONENT_VARIABLE = re.compile(r"\{\{.+?\}\}")
_POSITIONAL_VARIABLE = re.compile(r"\{\{\s*(\d+)\s*\}\}")


def _text_has_variable(text: str) -> bool:
    """Meta rejects a component example (error 2388043) when the text has no placeholder."""
    return bool(_COMPONENT_VARIABLE.search(text or ""))


def _example_values_for_text(text: str, params: Any) -> Any:
    """Drop example values that no longer match placeholders left in the text.

    An edit can remove ``{{n}}`` and still submit the previous ``body_params``.
    Meta requires the example length to equal the positional placeholders.
    """
    if not isinstance(params, list):
        return params

    placeholder_count = len(
        {int(match) for match in _POSITIONAL_VARIABLE.findall(text)}
    )
    if not placeholder_count:
        return params
    return list(params)[:placeholder_count]


class BodyTransformer(ComponentTransformer):
    """Transforms body component from library to translation format."""

    def transform(self, template_data: Dict) -> Optional[Dict]:
        if not template_data.get("body"):
            return None

        body_text = template_data["body"]
        body_data = {"type": "BODY", "text": body_text}
        body_params = template_data.get("body_params")

        if body_params and _text_has_variable(body_text):
            body_data["example"] = {
                "body_text": [_example_values_for_text(body_text, body_params)]
            }

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

    def _passthrough_translated_url_button(self, button: Dict) -> Dict:
        """Keep a URL that is already flat, without a stale example.

        Edits round-trip the stored button. An example on a URL that no
        longer contains ``{{n}}`` is Meta error 2388043.
        """
        translated = {
            "type": button["type"],
            "text": button.get("text"),
            "url": button["url"],
        }
        if _text_has_variable(button["url"]) and button.get("example"):
            translated["example"] = button["example"]
        return translated

    def _assign_url(self, button: Dict, url_data: Dict) -> None:
        """Attach the URL and, only when it has a placeholder, its example.

        A suffix example injects ``{{1}}``. A blank suffix is a static URL:
        sending ``example`` without a placeholder is Meta error 2388043.
        """
        base_url = ensure_protocol(url_data["base_url"])
        suffix_example = url_data.get("url_suffix_example")
        if not isinstance(suffix_example, str) or not suffix_example.strip():
            button["url"] = base_url
            return

        button["url"] = append_placeholder_if_needed(base_url)
        button["example"] = [normalize_url_if_needed(suffix_example)]

    def transform(self, template_data: Dict) -> Optional[List[Dict]]:
        buttons = template_data.get("buttons")

        if buttons is None:
            return None

        buttons_data = []

        for btn in buttons:
            if self._is_button_format_already_translated(btn):
                buttons_data.append(self._passthrough_translated_url_button(btn))
                continue

            button = {"type": btn["type"], "text": btn["text"]}

            if btn["type"] == "URL":
                self._assign_url(button, btn["url"])

            elif btn["type"] == "PHONE_NUMBER":
                button["phone_number"] = btn["phone_number"]
                button["country_code"] = btn.get("country_code", "55")

            elif btn["type"] == "PAYMENT_REQUEST":
                if btn.get("payment_setting"):
                    button["payment_setting"] = btn["payment_setting"]

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
