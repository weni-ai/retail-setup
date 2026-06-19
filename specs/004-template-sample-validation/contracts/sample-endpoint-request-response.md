# Contract: Sample Validation Endpoint (Frontend ↔ Retail)

**Feature**: `004-template-sample-validation`
**Spec**: `../spec.md`
**Plan**: `../plan.md`

This document pins the wire contract between the frontend caller
and the new Retail endpoint. Any change to this shape requires a
spec revision and a coordinated frontend deploy.

---

## Endpoint

```
POST /api/v3/templates/{template_uuid}/sample/
```

| Header              | Value                                                          | Required |
|---------------------|----------------------------------------------------------------|----------|
| `Authorization`     | `Bearer <jwt>`                                                 | Yes      |
| `Project-Uuid`      | The project UUID (consumed by `HasProjectPermission`)          | Yes      |
| `Content-Type`      | `application/json`                                             | Yes      |

The `template_uuid` path parameter is the SAME identifier the
existing `PATCH /api/v3/templates/<uuid>/` endpoint accepts.

---

## Request body

The request body schema is byte-for-byte compatible with
`UpdateTemplateContentSerializer` (FR-003) plus the additional
length-cap + button-mode validations from FR-003a applied at the
new endpoint only. The frontend can serialize the SAME form state
it sends to the legacy `PATCH` endpoint.

```jsonc
{
  // string, optional but at least one of body/header/footer required
  // Max 1024 chars (Meta cap, FR-003a)
  "template_body": "Olá {{1}}, seu pedido #{{2}} foi enviado e chega amanhã",

  // string, optional. Max 60 chars when TEXT; URL/base64-data-URI when IMAGE
  "template_header": "Pedido entregue",

  // string, optional. Max 60 chars (Meta cap, FR-003a)
  "template_footer": "Equipe Loja XYZ",

  // list[object], optional. Either ≤1 URL button OR ≤3 QUICK_REPLY buttons; NOT mixed.
  // Each button.text ≤ 20 chars (Meta cap, FR-003a)
  "template_button": [
    {
      "type": "URL",
      "text": "Confirmar recebimento",
      "url": {
        "base_url": "https://loja.example.com/confirmar",
        "url_suffix_example": "abc123"
      }
    }
  ],

  // list, optional. Used by BodyTransformer's example field (Meta-side body params).
  // ALSO used as the positional substitution source for {{N}} placeholders
  // in body/header/footer/button text+url on the OUTBOUND sample (A7 / FR-004e).
  "template_body_params": ["João", "1234"],

  // string, REQUIRED. Integrations engine app UUID (per existing PATCH endpoint)
  "app_uuid": "a1b2c3d4-1111-2222-3333-444455556666",

  // string, REQUIRED. Project UUID (per existing PATCH endpoint, also in Project-Uuid header)
  "project_uuid": "11111111-2222-3333-4444-555566667777",

  // list[{name, value}], optional. Custom-template rule-engine parameters.
  // NOT consulted for outbound substitution (Research Decision 9).
  "parameters": null,

  // string, optional. Locale for the new Version.
  // Falls back to agent_config + project defaults via resolve_template_language.
  "language": "pt_BR"
}
```

### Validation rules (HTTP 400 on failure)

| Rule (FR ref)                                               | Failure response                                                                                                                  |
|-------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| At least one of `template_body`/`template_header`/`template_footer` set (FR-003 — inherited from `UpdateTemplateContentSerializer.validate`) | DRF default field-level error                                                                                                     |
| `app_uuid` and `project_uuid` present (FR-003)              | DRF default field-level error                                                                                                     |
| `template_body` ≤ 1024 chars (FR-003a)                      | DRF default field-level error                                                                                                     |
| `template_header` ≤ 60 chars when TEXT (FR-003a)            | DRF default field-level error                                                                                                     |
| `template_footer` ≤ 60 chars (FR-003a)                      | DRF default field-level error                                                                                                     |
| Each button's `text` ≤ 20 chars (FR-003a)                   | DRF default field-level error                                                                                                     |
| ≤ 1 `URL`-type button (FR-003a)                             | DRF default field-level error                                                                                                     |
| ≤ 3 `QUICK_REPLY`-type buttons (FR-003a)                    | DRF default field-level error                                                                                                     |
| No mixing `URL` + `QUICK_REPLY` types in a single payload (FR-003a) | DRF default field-level error                                                                                                     |
| `Project-Uuid` header MUST equal body `project_uuid` (FR-002b — SC-008 cross-tenant isolation) | `{"detail": "Project-Uuid header does not match body project_uuid", "error_code": "project_uuid_mismatch"}` (HTTP 400) |
| `template_uuid` path param resolves to a real Template      | DRF default `NotFound` → HTTP 404                                                                                                  |

---

## Response — HTTP 200 (UTILITY-classified sample)

```jsonc
{
  // Meta's verdict verbatim
  "category": "UTILITY",

  // true — the local update was applied
  "template_updated": true,

  // ReadTemplateSerializer shape — same fields the existing
  // PATCH endpoint returns today on success. The frontend can
  // substitute this directly into its template-display state
  // without re-fetching (SC-005).
  "template": {
    "uuid": "0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11",
    "name": "weni_order_delivered",
    "display_name": "Order delivered",
    "start_condition": "order.status == \"delivered\"",

    // status is "APPROVED" per FR-006d — the new Version is
    // persisted with APPROVED directly, current_version is
    // repointed inline. No PENDING transitional state.
    "status": "APPROVED",
    "rule_code": "...",
    "metadata": {
      // body retains raw {{N}} placeholders per A7
      "body": "Sua entrega chegou! Confirme o recebimento clicando no botão abaixo.",
      "body_params": null,
      "header": { "header_type": "TEXT", "text": "Pedido entregue" },
      "footer": "Equipe Loja XYZ",
      // buttons in canonical local shape — {type, text, url}
      // (Meta's wire shape is interactive.action.parameters.{display_text, url}
      // and is NOT persisted)
      "buttons": [
        {
          "type": "URL",
          "text": "Confirmar recebimento",
          "url": "https://loja.example.com/confirmar/{{1}}",
          "example": ["abc123"]
        }
      ],
      "category": "UTILITY",
      "language": "pt_BR"
    },
    "is_custom": false,
    "needs_button_edit": false,
    "deleted_at": null,
    "is_active": true,
    "variables": []
  },

  // Raw JSON body Meta returned — so the operator can see
  // Meta's exact answer. Schema may evolve as Meta adds fields.
  "meta_sample_response": {
    "success": true,
    "category": "UTILITY"
  }
}
```

---

## Response — HTTP 200 (non-UTILITY-classified sample)

```jsonc
{
  // Meta's non-UTILITY verdict verbatim (MARKETING, AUTHENTICATION,
  // or any future value Meta may introduce)
  "category": "MARKETING",

  // false — no local update was applied
  "template_updated": false,

  // ReadTemplateSerializer shape for the UNCHANGED template.
  // metadata reflects the pre-call state; current_version
  // pointer is unchanged.
  "template": {
    "uuid": "0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11",
    "status": "APPROVED",
    "metadata": {
      "body": "Olá {{1}}, seu pedido foi confirmado",
      "category": "UTILITY",
      "language": "pt_BR"
    }
    // ... other fields unchanged
  },

  "meta_sample_response": {
    "success": true,
    "category": "MARKETING"
  }
}
```

---

## Response — HTTP 400 (invalid request)

Four error_code variants, all under HTTP 400:

### Serializer-level validation failure (FR-007c)

DRF default field-level error body:

```jsonc
{
  "template_body": ["Ensure this field has no more than 1024 characters."],
  "template_button": ["Cannot mix URL and QUICK_REPLY buttons in a single sample."]
}
```

### Template is not Direct Send-eligible (FR-007e / FR-002a)

```jsonc
{
  "detail": "Template is not Direct Send-eligible",
  "error_code": "not_direct_send_eligible"
}
```

Fires when:
- `template.integrated_agent IS NULL` (custom template never
  assigned to an IntegratedAgent), OR
- `template.integrated_agent.config.get("direct_send", False)` is
  `False` / missing (legacy IntegratedAgent assigned before the
  Direct Send rollout).

### Project-Uuid header / body project_uuid mismatch (FR-007f / FR-002b)

```jsonc
{
  "detail": "Project-Uuid header does not match body project_uuid",
  "error_code": "project_uuid_mismatch"
}
```

Fires when the `Project-Uuid` HTTP header (the trust source for
`HasProjectPermission`) does not equal the `project_uuid` field in
the request body (the source used by FR-005a for WABA resolution).
The check runs at the serializer layer BEFORE any DB lookup or
Meta call. This is the SC-008 cross-tenant isolation guard — an
operator authorized for project A cannot route a sample call to
project B's WABA.

### WABA not configured for project (FR-007d / FR-005a)

```jsonc
{
  "detail": "WABA not configured for this project",
  "error_code": "waba_not_configured"
}
```

Fires when any of the following resolve to a missing / empty
`waba_id` (per the 2026-05-26 clarification, all three collapse to
this single user-facing response; the audit log's
`integrations_response_present` field discriminates the underlying
mode — see `data-model.md` §7):

- The Connect-side `IntegrationsService.get_channel_app("wpp-cloud", app_uuid)`
  call fails (HTTP 5xx / network timeout / connection error —
  swallowed to `None` by the service), OR
- The integrations call returns no app for the supplied
  `app_uuid` (also surfaces as `None`), OR
- The integrations call returns an app whose
  `config["waba"]["id"]` is missing / `None` / empty.

`ProjectOnboarding` is NOT consulted for WABA resolution by this
endpoint; the integrations engine is the authoritative source.

---

## Response — HTTP 404 (template not found)

DRF default NotFound:

```jsonc
{
  "detail": "Template not found: 0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11"
}
```

Parity with the legacy `PATCH /api/v3/templates/<uuid>/` endpoint
per FR-011.

---

## Response — HTTP 401 / 403 (auth failure)

DRF defaults from `IsAuthenticated` + `HasProjectPermission`. No
custom handling.

---

## Response — HTTP 502 (Meta-side failure)

Two error_code variants, both under HTTP 502.

### Meta sample submission failed (FR-007b / FR-005c)

Fires on `CustomAPIException` from the Meta client (HTTP 5xx,
network timeout, etc.):

```jsonc
{
  "detail": "Meta sample submission failed",
  "error_code": "meta_unavailable",

  // Present when the upstream provided ANY parseable body, including
  // an empty object {}. Omitted only when the upstream provided no
  // body at all (the view checks `exc.meta_response is not None`,
  // not truthiness, so {} is surfaced verbatim). Schema mirrors
  // Meta's error envelope.
  "meta_response": {
    "error": {
      "message": "Internal server error",
      "type": "OAuthException",
      "code": 1,
      "fbtrace_id": "ARTCDsilOnw0CnIEuIq4_No"
    }
  }
}
```

### Meta returned 200 but no category field (FR-005c)

Fires when Meta's response body lacks `category` or carries
`success: false`:

```jsonc
{
  "detail": "Meta did not return a category",
  "error_code": "meta_invalid_response",

  // Always present. The raw body Meta returned, for debugging.
  "meta_response": {
    "success": false,
    "error": {
      "code": 2388341,
      "message": "Samples API Access is restricted"
    }
  }
}
```

---

## Response — HTTP 500 (unexpected local failure)

Fires only when a UTILITY classification has been received from
Meta and the LOCAL update fails (DB write fails, S3 upload fails,
etc. — per FR-006c). The audit log emits
`local_update_failed_after_meta_approval` with `exc_info=True`.
DRF default error body. The operator should retry; Meta's sample
endpoint is idempotent so re-submission is safe (A6).

---

## Idempotency & retry semantics

The endpoint is NOT idempotent at the local-write level. Each
call:

- ALWAYS fires the outbound Meta sample request (no client-side
  deduplication). Concurrent calls from a single operator
  consume Meta sample-API quota proportionally.
- ALWAYS creates a new `Version` row on UTILITY (`_create_version`
  does not dedup on content per the existing legacy behavior).
- ALWAYS advances `Template.current_version` on UTILITY.

The frontend SHOULD serialize concurrent edits to the same
template (e.g. only one edit dialog open at a time per template).
The backend does NOT enforce serialization; concurrent UTILITY
classifications resolve under last-writer-wins with both new
Version rows preserved in `Template.versions` history (spec.md
Edge Case).

## Latency expectations

| Percentile | Latency (steady state) |
|------------|------------------------|
| p50        | ~600ms                 |
| p90        | ~1.2s                  |
| p99        | <3s (SC-006)           |

The dominant contributor is the outbound Meta call. Retail's local
hot path is bounded structurally by 2 DB reads + 3–4 DB writes +
optional 1 S3 upload (when an IMAGE header is base64).
