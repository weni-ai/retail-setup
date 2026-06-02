"""Per-``(template_name, language)`` URL-button label override map.

Source of truth for the FR-003g remediation table. Consumed by
``_meta_library_template_fetch._resolve_url_button_label_override``.
Adding entries is a spec amendment (FR-003g(g)); see
``specs/002-direct-send-broadcasts/spec.md`` for the normative rules.
"""

DIRECT_SEND_BUTTON_LABEL_OVERRIDES: dict[tuple[str, str], str] = {
    ("order_canceled_3", "pt_BR"): "Detalhes do pedido",
    ("order_canceled_3", "es"): "Detalles del pedido",
}
