"""Language-aware labels for the rendered contract-acceptance PDF.

The mapping key is the language prefix (e.g. "pt", "en", "es") extracted
from the project language field (e.g. "pt-br" -> "pt"). Falls back to
"en" when the prefix is not found.
"""

import logging
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from html import escape

from django.utils import timezone as dj_timezone

logger = logging.getLogger(__name__)

FALLBACK_LANGUAGE = "en"

UTC_OFFSET_PATTERN = re.compile(r"^([+-])(\d{2}):(\d{2})$")

CONTRACTOR_LEGAL = {
    "company": "VTEX Brasil Tecnologia para E-commerce Ltda.",
    "tax_id": "05.359.861/0001-82",
    "platform_name": "VTEX CX",
    "footer": "VTEX CX Platform",
}

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
        "record_title": "ELECTRONIC ACCEPTANCE RECORD",
        "contractor_heading": "CONTRACTOR",
        "provider_heading": "PROVIDER",
        "company": "Company",
        "responsible_user": "Responsible user",
        "source_ip": "Source IP",
        "tax_id": "Tax ID",
        "contract_version": "Contract version",
        "acceptance_id": "Acceptance ID",
        "location_city": "São Paulo",
        "electronic_acceptance_label": "Electronic acceptance",
        "legal_notice": (
            "This document was accepted electronically on {accepted_at_formatted} "
            "by checking the agreement checkbox on the {platform_name} platform. "
            "The complete record of this acceptance, including source IP, user "
            "agent and timestamp, is stored under ID {acceptance_id}."
        ),
    },
    "pt": {
        "title": "Contrato de adesão",
        "version": "Versão",
        "vtex_account": "Conta da loja",
        "email": "E-mail",
        "plan": "Plano contratado",
        "accepted_at": "Data do aceite",
        "offset": "offset",
        "acceptance_prefix": "Registro de aceite vinculado à conta",
        "acceptance_on": "em",
        "record_title": "REGISTRO DE ACEITE ELETRÔNICO",
        "contractor_heading": "CONTRATANTE",
        "provider_heading": "CONTRATADA",
        "company": "Empresa",
        "responsible_user": "Usuário responsável",
        "source_ip": "IP de origem",
        "tax_id": "CNPJ",
        "contract_version": "Versão do contrato",
        "acceptance_id": "ID do aceite",
        "location_city": "São Paulo",
        "electronic_acceptance_label": "Aceite eletrônico",
        "legal_notice": (
            "Este documento foi aceito eletronicamente em {accepted_at_formatted} "
            "mediante marcação de checkbox de concordância na plataforma "
            "{platform_name}, em conformidade com a MP 2.200-2/2001. O aceite "
            "eletrônico tem validade jurídica equivalente à assinatura manuscrita "
            "nos termos da legislação brasileira vigente. O registro completo "
            "deste aceite, incluindo IP de origem, user agent e timestamp, está "
            "armazenado com ID {acceptance_id}."
        ),
    },
    "es": {
        "title": "Contrato de adhesión",
        "version": "Versión",
        "vtex_account": "Cuenta de la tienda",
        "email": "Correo electrónico",
        "plan": "Plan contratado",
        "accepted_at": "Fecha de aceptación",
        "offset": "offset",
        "acceptance_prefix": "Registro de aceptación vinculado a la cuenta",
        "acceptance_on": "el",
        "record_title": "REGISTRO DE ACEPTACIÓN ELECTRÓNICA",
        "contractor_heading": "CONTRATANTE",
        "provider_heading": "CONTRATADA",
        "company": "Empresa",
        "responsible_user": "Usuario responsable",
        "source_ip": "IP de origen",
        "tax_id": "CNPJ",
        "contract_version": "Versión del contrato",
        "acceptance_id": "ID de aceptación",
        "location_city": "São Paulo",
        "electronic_acceptance_label": "Aceptación electrónica",
        "legal_notice": (
            "Este documento fue aceptado electrónicamente el "
            "{accepted_at_formatted} mediante la selección del checkbox de "
            "aceptación en la plataforma {platform_name}. El registro completo "
            "de esta aceptación, incluidos IP de origen, user agent y "
            "timestamp, se almacena con ID {acceptance_id}."
        ),
    },
}

PT_MONTHS = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)

ES_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

EN_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


ORDER_FORM_PARTIALS = {
    "en": "contract/pdf/partials/order_form_body_en.html",
    "pt": "contract/pdf/partials/order_form_body_pt.html",
    "es": "contract/pdf/partials/order_form_body_es.html",
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


def get_order_form_partial(language: str) -> str:
    """Return the Order Form body partial template for the given language."""
    return ORDER_FORM_PARTIALS[resolve_language_prefix(language)]


def apply_local_offset(accepted_at: datetime, local_offset: str) -> datetime:
    """Shift a UTC timestamp by the subscriber's UTC offset string."""
    match = UTC_OFFSET_PATTERN.match(local_offset or "")
    if not match:
        return accepted_at

    sign, hours, minutes = match.groups()
    delta = timedelta(hours=int(hours), minutes=int(minutes))
    if sign == "-":
        delta = -delta

    base = accepted_at
    if dj_timezone.is_naive(base):
        base = dj_timezone.make_aware(base, dt_timezone.utc)
    return base + delta


def format_acceptance_date_only(
    accepted_at: datetime, local_offset: str, language: str
) -> str:
    """Format the acceptance date for the Order Form signature line."""
    local_dt = apply_local_offset(accepted_at, local_offset)
    prefix = resolve_language_prefix(language)

    if prefix == "pt":
        month = PT_MONTHS[local_dt.month - 1]
        return f"{local_dt.day} de {month} de {local_dt.year}"

    if prefix == "es":
        month = ES_MONTHS[local_dt.month - 1]
        return f"{local_dt.day} de {month} de {local_dt.year}"

    month = EN_MONTHS[local_dt.month - 1]
    return f"{month} {local_dt.day}, {local_dt.year}"


def format_acceptance_datetime(
    accepted_at: datetime, local_offset: str, language: str
) -> str:
    """Format acceptance timestamp for the electronic record section."""
    local_dt = apply_local_offset(accepted_at, local_offset)
    prefix = resolve_language_prefix(language)
    utc_label = f"UTC{local_offset}"

    if prefix == "pt":
        month = PT_MONTHS[local_dt.month - 1]
        return (
            f"{local_dt.day} de {month} de {local_dt.year}, "
            f"às {local_dt.hour}h{local_dt.minute:02d}min ({utc_label})"
        )

    if prefix == "es":
        month = ES_MONTHS[local_dt.month - 1]
        return (
            f"{local_dt.day} de {month} de {local_dt.year}, "
            f"a las {local_dt.hour:02d}:{local_dt.minute:02d} ({utc_label})"
        )

    month = EN_MONTHS[local_dt.month - 1]
    hour = local_dt.strftime("%I").lstrip("0") or "12"
    period = local_dt.strftime("%p")
    return (
        f"{month} {local_dt.day}, {local_dt.year}, "
        f"at {hour}:{local_dt.minute:02d} {period} ({utc_label})"
    )


def build_electronic_acceptance_notice(
    language: str,
    accepted_at: datetime,
    local_offset: str,
    acceptance_id: str,
) -> str:
    """Build the localized legal notice for the PDF acceptance record."""
    labels = get_contract_pdf_labels(language)
    accepted_at_formatted = format_acceptance_datetime(
        accepted_at, local_offset, language
    )
    return labels["legal_notice"].format(
        accepted_at_formatted=accepted_at_formatted,
        platform_name=CONTRACTOR_LEGAL["platform_name"],
        acceptance_id=acceptance_id,
    )


def build_contract_email(
    language: str, plan_name: str, contract_version: str, accepted_at
) -> dict:
    """Build the localized email subject and HTML body for an acceptance.

    The whole email is composed here so the downstream sender (Connect)
    only has to deliver it; both the PDF and the email therefore speak the
    same language.
    """
    config = CONTRACT_EMAIL_TRANSLATIONS[resolve_language_prefix(language)]
    body = config["body"].format(
        plan=escape(plan_name or "-"),
        version=escape(contract_version),
        date=accepted_at.strftime(config["date_format"]),
    )
    return {"subject": config["subject"], "body_html": body}
