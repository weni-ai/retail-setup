"""Language-aware labels for the rendered contract-acceptance PDF.

The mapping key is the language prefix (e.g. "pt", "en", "es") extracted
from the project language field (e.g. "pt-br" -> "pt"). Falls back to
"en" when the prefix is not found.
"""

import logging
from html import escape

logger = logging.getLogger(__name__)

FALLBACK_LANGUAGE = "en"

CONTRACT_PDF_TRANSLATIONS = {
    "en": {
        "title": "Membership agreement",
        "version": "Version",
        "vtex_account": "Store account",
        "email": "Subscriber email",
        "plan": "Contracted plan",
        "accepted_at": "Acceptance date",
        "offset": "offset",
        "acceptance_prefix": "Acceptance recorded for account",
        "acceptance_on": "on",
    },
    "pt": {
        "title": "Contrato de adesão",
        "version": "Versão",
        "vtex_account": "Conta da loja",
        "email": "E-mail do contratante",
        "plan": "Plano contratado",
        "accepted_at": "Data do aceite",
        "offset": "offset",
        "acceptance_prefix": "Registro de aceite vinculado à conta",
        "acceptance_on": "em",
    },
    "es": {
        "title": "Contrato de adhesión",
        "version": "Versión",
        "vtex_account": "Cuenta de la tienda",
        "email": "Correo del contratante",
        "plan": "Plan contratado",
        "accepted_at": "Fecha de aceptación",
        "offset": "offset",
        "acceptance_prefix": "Registro de aceptación vinculado a la cuenta",
        "acceptance_on": "el",
    },
}


CONTRACT_EMAIL_TRANSLATIONS = {
    "en": {
        "subject": "Your contract",
        "body": (
            "<p>Hello,</p>"
            "<p>Your contract acceptance has been registered.</p>"
            "<p>Plan: {plan}<br/>Version: {version}<br/>Date: {date}</p>"
            "<p>The accepted document is attached to this email.</p>"
        ),
        "date_format": "%m/%d/%Y",
    },
    "pt": {
        "subject": "Seu contrato",
        "body": (
            "<p>Olá,</p>"
            "<p>Seu aceite de contrato foi registrado.</p>"
            "<p>Plano: {plan}<br/>Versão: {version}<br/>Data: {date}</p>"
            "<p>O documento aceito está anexado a este e-mail.</p>"
        ),
        "date_format": "%d/%m/%Y",
    },
    "es": {
        "subject": "Tu contrato",
        "body": (
            "<p>Hola,</p>"
            "<p>Tu aceptación de contrato fue registrada.</p>"
            "<p>Plan: {plan}<br/>Versión: {version}<br/>Fecha: {date}</p>"
            "<p>El documento aceptado está adjunto a este correo.</p>"
        ),
        "date_format": "%d/%m/%Y",
    },
}


def resolve_language_prefix(language: str) -> str:
    """Return a supported language prefix, falling back to English."""
    prefix = (language or "").split("-")[0].lower()
    if prefix not in CONTRACT_PDF_TRANSLATIONS:
        if prefix:
            logger.warning(
                f"Unsupported contract language '{language}'. "
                f"Falling back to '{FALLBACK_LANGUAGE}'."
            )
        return FALLBACK_LANGUAGE
    return prefix


def get_contract_pdf_labels(language: str) -> dict:
    """Return the PDF labels for the given project language."""
    return CONTRACT_PDF_TRANSLATIONS[resolve_language_prefix(language)]


def build_contract_email(
    language: str, plan_name: str, contract_version: str, accepted_at
) -> dict:
    """Build the localized email subject and HTML body for an acceptance.

    The whole email is composed here so the downstream sender (Connect)
    only has to deliver it; both the PDF and the email therefore speak the
    same language.
    """
    config = CONTRACT_EMAIL_TRANSLATIONS[resolve_language_prefix(language)]
    # Connect delegates HTML sanitization to the caller, so escape every
    # interpolated value before embedding it in the email body.
    body = config["body"].format(
        plan=escape(plan_name or "-"),
        version=escape(contract_version),
        date=accepted_at.strftime(config["date_format"]),
    )
    return {"subject": config["subject"], "body_html": body}
