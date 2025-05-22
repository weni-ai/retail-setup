from typing import Dict, Optional


def adapt_library_template_to_translation(template_data: Dict) -> Dict:
    """
    Adapts a message_template_library (pre-approved) template metadata to the format
    required for template translation creation in the integrations module.

    Args:
        template_data (dict): The original metadata from the template.

    Returns:
        dict: translation_payload formatted for integrations.
    """
    language = template_data.get("language", "pt_BR")

    # Header component (optional)
    header_data = None
    if template_data.get("header"):
        header_data = {"header_type": "TEXT", "text": template_data["header"]}

    # Body component (required)
    body_data = {"type": "BODY", "text": template_data["body"]}

    # Add parameter examples for body if available
    if "body_params" in template_data:
        body_data["example"] = {"body_text": [template_data["body_params"]]}

    # Footer component (optional)
    footer_data: Optional[Dict] = None
    if template_data.get("footer"):
        footer_data = {"type": "FOOTER", "text": template_data["footer"]}

    # Buttons component (optional)
    buttons_data = []
    for btn in template_data.get("buttons", []):
        button = {"button_type": btn["type"], "text": btn["text"]}

        if btn["type"] == "URL":
            button["url"] = btn["url"]
        elif btn["type"] == "PHONE_NUMBER":
            button["phone_number"] = btn["phone_number"]
            button["country_code"] = btn.get("country_code", "55")

        buttons_data.append(button)

    # Final translation payload
    translation_payload = {
        "language": language,
        "header": header_data,
        "body": body_data,
    }

    if footer_data:
        translation_payload["footer"] = footer_data
    if buttons_data:
        translation_payload["buttons"] = buttons_data

    return translation_payload
