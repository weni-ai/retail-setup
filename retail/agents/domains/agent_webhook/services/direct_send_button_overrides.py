"""Per-``(template_name, language)`` button-label override map (FR-003g).

A small data-driven map consulted at fetch time inside
``_validate_and_normalize_buttons`` ONLY when an upstream URL button's
``text`` for an entry of ``type == "URL"`` would otherwise fail the
existing ``MAX_BUTTON_LABEL_LENGTH`` check (Session 2026-05-22 Q5–Q9).

Scope and rules (FR-003g(a)–(h)):

- The override applies EXCLUSIVELY to the single URL button per template
  (FR-003f caps URL count at ≤1). QUICK_REPLY overflows continue to
  raise per FR-003f.c — the override mechanism is NOT in scope for
  QUICK_REPLY in v1.
- The override is consulted ONLY when the upstream label would
  otherwise overflow. Labels that already fit the 20-char ceiling are
  persisted verbatim; the map is NEVER consulted in that case
  (FR-003g(b) "trigger conditional on overflow").
- An override value that itself exceeds ``MAX_BUTTON_LABEL_LENGTH``
  MUST raise ``DirectSendUnsupportedComponentError(component_type="buttons")``
  — the override is a remediation, not a length-check bypass
  (FR-003g(h)).
- Per-call branching on ``template_name`` inside the adapter is
  forbidden (FR-003g(a)). The adapter consults the map ONLY via
  ``(template_name, language)`` lookup.
- Audit is INFO-log-only at the override site; no flag is persisted on
  ``Template.metadata.direct_send`` (FR-003g(f)).

Adding any further entry is a spec amendment (FR-003g(g)).
"""

DIRECT_SEND_BUTTON_LABEL_OVERRIDES: dict[tuple[str, str], str] = {
    ("order_canceled_3", "pt_BR"): "Detalhes do pedido",
    ("order_canceled_3", "es"): "Detalles del pedido",
}
