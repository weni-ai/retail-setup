# Contract: Meta `message_samples` API (Retail → Meta)

**Feature**: `004-template-sample-validation`
**Spec**: `../spec.md`
**Plan**: `../plan.md`
**Source**: `docs/direct-send-api-beta-integration.md:567-685` and
<https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/interactive-cta-url-messages>

This document pins the wire contract between Retail and Meta's
`message_samples` endpoint. Any divergence between this contract
and Meta's actual API would surface as a `meta_invalid_response`
or `meta_unavailable` HTTP 502 to the frontend.

---

## Endpoint

```
POST https://graph.facebook.com/{API_VERSION}/{WABA_ID}/message_samples
```

| Header              | Value                                                          | Required |
|---------------------|----------------------------------------------------------------|----------|
| `Authorization`     | `Bearer {META_SYSTEM_USER_ACCESS_TOKEN}`                       | Yes      |
| `Content-Type`      | `application/json`                                             | Yes      |

`API_VERSION` defaults to whatever `META_API_URL` is set to today
(used by `MetaClient.create_flow`, `MetaClient.publish_flow`).
`WABA_ID` is resolved per-call from
`ProjectOnboarding.config["channels"]["wpp-cloud"]["channel_data"]["waba_id"]`
per FR-005a / data-model.md §3.

---

## Request body — three discriminated-union shapes

The wire body is built by the new pure-function translator
`retail.templates.adapters.direct_send_sample_translator.build_meta_sample_body`
per FR-004 / FR-004a / FR-004e. Variable substitution
(`{{1}}`, `{{2}}`, ...) happens BEFORE assembling the wire body
using `template_body_params` (Research Decision 9 / A7).

### Shape 1 — text-only (no header, no footer, no buttons)

Per `docs/direct-send-api-beta-integration.md:579-586`:

```jsonc
{
  "type": "text",
  "text": {
    // Substituted body — placeholders {{N}} replaced with template_body_params[N-1]
    "body": "Olá João, seu pedido #1234 foi enviado e chega amanhã"
  }
}
```

Fires when the input payload has `template_body` set AND no
`template_header` AND no `template_footer` AND no `template_button`.

### Shape 2 — interactive CTA URL button

Per `docs/direct-send-api-beta-integration.md:588-628` and the
dev-docs CTA URL reference linked above:

```jsonc
{
  "type": "interactive",
  "interactive": {
    "type": "cta_url",

    // Optional. Discriminated union — type ∈ {text, image}.
    // For text headers: {"type": "text", "text": <substituted>}.
    // For image headers: {"type": "image", "image": {"link": <s3_url>}}.
    //   The base64 → S3 upload happens BEFORE this translator runs (A9).
    "header": {
      "type": "text",
      "text": "Pedido entregue"
    },

    // Mandatory. Body text (substituted).
    "body": { "text": "Olá João, seu pedido #1234 foi entregue." },

    // Optional. Footer text (substituted, but typically static).
    "footer": { "text": "Equipe Loja XYZ" },

    // Mandatory. The CTA URL action.
    "action": {
      "name": "cta_url",
      "parameters": {
        // Substituted button label
        "display_text": "Confirmar recebimento",
        // Fully-resolved URL — base_url + {{1}} placeholder substitution
        // if url_suffix_example was supplied, with template_body_params[0]
        // substituted (FR-004b / FR-004e)
        "url": "https://loja.example.com/confirmar/1234"
      }
    }
  }
}
```

Fires when the input payload has exactly one `template_button`
entry of `type == "URL"`.

### Shape 3 — interactive reply buttons

Per `docs/direct-send-api-beta-integration.md:630-674`:

```jsonc
{
  "type": "interactive",
  "interactive": {
    "type": "button",

    // Optional. Same shape as Shape 2's header.
    "header": {
      "type": "image",
      "image": { "link": "https://retail-bucket.s3.amazonaws.com/template_headers/abc123.png" }
    },

    // Mandatory. Body text (substituted).
    "body": { "text": "Pedido #1234 confirmado. Como você gostaria de prosseguir?" },

    // Optional. Footer text.
    "footer": { "text": "..." },

    // Mandatory. The reply-buttons action.
    "action": {
      "buttons": [
        {
          "type": "reply",
          "reply": {
            // Deterministic id derived from text (FR-004c):
            //   1. lowercase
            //   2. strip non-alphanumeric → underscore
            //   3. truncate to a safe length cap (e.g. 256 chars, well under Meta's max)
            //   4. on duplicate-within-payload: append _2, _3, ... positional suffix
            "id": "ver_detalhes",
            "title": "Ver detalhes"
          }
        },
        {
          "type": "reply",
          "reply": {
            "id": "cancelar_pedido",
            "title": "Cancelar pedido"
          }
        }
      ]
    }
  }
}
```

Fires when the input payload has 1–3 `template_button` entries of
`type == "QUICK_REPLY"`.

---

## Header sub-object discriminated union (Shape 2 + Shape 3)

Per `docs/direct-send-api-beta-integration.md:599-610`:

| Local header shape (input `template_header`) | Meta wire shape (output)                                      |
|-----------------------------------------------|---------------------------------------------------------------|
| Plain text (≤60 chars)                        | `{"type": "text", "text": "<substituted text>"}`              |
| HTTP(S) URL pointing to an image              | `{"type": "image", "image": {"link": "<url>"}}`               |
| Base64-data-URI (e.g. `data:image/png;base64,...`) | Upload to S3 via `TemplateMetadataHandler._upload_header_image` (FR-004a / A9), then `{"type": "image", "image": {"link": "<resolved_s3_url>"}}` |
| Existing S3 URL (already uploaded)            | `{"type": "image", "image": {"link": "<existing_url>"}}`      |

The use case calls `_upload_header_image` BEFORE invoking the
translator so the translator stays I/O-free (Research Decision 6).
The upload result is passed via the optional
`resolved_header_url` parameter on `build_meta_sample_body`. On
non-IMAGE headers the parameter is ignored.

`media_id` is NOT used by this endpoint — we always resolve to a
public URL via the existing S3 upload path before sending the
sample (FR-004a / A9).

---

## Response — happy path (HTTP 200 from Meta)

Per `docs/direct-send-api-beta-integration.md:680-685`:

```jsonc
{
  "success": true,
  "category": "UTILITY"  // or "MARKETING" / "AUTHENTICATION"
}
```

Retail's classification rule (FR-005b):

| Meta response                                               | Retail's classification                                           |
|-------------------------------------------------------------|-------------------------------------------------------------------|
| `category == "UTILITY"`                                     | UTILITY → local update fires                                      |
| `category` set to any other non-empty string                | NOT-UTILITY → local update does NOT fire                          |
| `category` missing / null / empty OR `success: false`       | INVALID → HTTP 502 / `meta_invalid_response`                      |

---

## Response — Meta-side failure (any non-2xx)

Per `docs/direct-send-api-beta-integration.md:976` (and Meta's
standard error envelope):

```jsonc
{
  "error": {
    "message": "Samples API Access is restricted",
    "type": "OAuthException",
    "code": 2388341,
    "fbtrace_id": "ARTCDsilOnw0CnIEuIq4_No"
  }
}
```

`MetaClient.submit_template_sample` raises `CustomAPIException`
with the parsed body attached. The service propagates it (Research
Decision 5 / plan Complexity Tracking row 1). The use case catches
and raises `MetaSampleUnavailableError` with `meta_response` set
to the parsed body. The view emits HTTP 502 with `error_code =
"meta_unavailable"` per FR-007b.

### Known Meta error codes (informational, not exhaustive)

| Code     | Meaning                                                                                                                                  | Operator action                                                                  |
|----------|------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| `2388341` | Samples API Access is restricted                                                                                                         | Contact `wadirectsendapisupport@meta.com` (per Meta docs)                        |
| `100`    | Request included one or more unsupported or misspelled parameters                                                                        | Likely a Retail-side bug — translator emitted an invalid shape. File an issue.   |
| `139200` | Direct Send Utility access is blocked due to misclassification-based enforcements                                                        | Contact `wadirectsendapisupport@meta.com`; resolve the WABA's category issues.   |
| `1`      | Generic infrastructure failure                                                                                                           | Retry; transient. If persistent, escalate to Meta.                              |

---

## Variable substitution rules (FR-004e / A7)

Before assembling the wire body, the translator substitutes every
`{{N}}` placeholder in:

- `template_body` → Shape 1's `text.body` / Shape 2's `interactive.body.text` / Shape 3's `interactive.body.text`
- `template_header` (when TEXT) → `interactive.header.text`
- `template_footer` → `interactive.footer.text`
- Each button's `text` → `interactive.action.parameters.display_text` (Shape 2) or `interactive.action.buttons[i].reply.title` (Shape 3)
- The URL button's `url` → `interactive.action.parameters.url` (Shape 2)

Substitution source: `template_body_params` (positional list mapped
to `{{1}}`, `{{2}}`, ...).

Substitution helper:
`retail.agents.domains.agent_webhook.services.direct_send_payload_builder.substitute_template_variables`
— the SAME helper the Direct Send broadcast renderer uses at
dispatch time. Reusing it guarantees the outbound Meta sample
matches what the actual broadcast would render (US2's lockstep
guarantee).

Missing indices substitute to empty string and emit a WARNING log
(matching the dispatch-time behavior). Operators are expected to
provide values for every placeholder they include (spec.md A7).

The LOCAL persisted `metadata` retains raw `{{N}}` placeholders
— substitution is OUTBOUND-ONLY (A7). The dispatch-time renderer
re-substitutes against per-contact `template_variables` at
broadcast time.

---

## Deterministic `reply.id` derivation (Shape 3 only)

Per FR-004c, each reply button's `reply.id` is derived
deterministically from `button.text`:

```text
1. lowercase: "Ver detalhes" → "ver detalhes"
2. strip non-alphanumeric to underscore: "ver detalhes" → "ver_detalhes"
3. collapse consecutive underscores: "ver__detalhes" → "ver_detalhes"
4. strip leading/trailing underscores: "_ver_detalhes_" → "ver_detalhes"
5. truncate to a safe cap (e.g. 256 chars; Meta's exact cap is
   undocumented in the beta docs, 256 is well below any plausible limit)
6. on duplicate-within-payload: append _2, _3, ... positional suffix
```

The `id` is for Meta's internal sample categorization and is
NEVER persisted locally (`Template.metadata.buttons[i]` carries
only `type`, `text`, and (for URL) `url` — see
`retail/templates/strategies/update_template_strategies.py`'s
`buttons` handling at lines 49-52).

---

## URL resolution for CTA URL buttons (Shape 2)

The translator delegates URL canonicalization to the existing
helpers per FR-004b:

- `ButtonTransformer._is_button_format_already_translated` →
  detect whether the input is already in the flat-string shape.
- `ensure_protocol(base_url)` → prepend `https://` if missing.
- If `url_suffix_example` is supplied: `append_placeholder_if_needed(base_url)` →
  append `{{1}}` placeholder.
- After `{{1}}` substitution per Variable substitution rules
  above: the final URL is fully resolved (no placeholder remains).

The canonical local-shape URL stored on
`Template.metadata.buttons[i].url` is the SAME string the legacy
`TemplateTranslationAdapter.adapt` would produce — preserving
US2's lockstep guarantee.

---

## What is NOT sent to Meta

- The local `template_uuid` is NOT included (Meta has no concept
  of Retail's local UUIDs).
- The `app_uuid` is NOT included (the WABA id is in the URL).
- The `project_uuid` is NOT included (same reason).
- `template_body_params` is NOT included verbatim (it's the
  substitution source; substituted values appear in the wire
  body but the source list is not echoed).
- `parameters` (custom-template rule-engine inputs) is NOT
  included (Research Decision 9).
- Any internal Retail identifier (Version uuid, IntegratedAgent
  uuid, etc.) is NOT included.

The Meta-side classification is content-only — Meta evaluates the
rendered text + image + button labels against its UTILITY
guidelines and returns the verdict. No tenant or resource
identifier from Retail's side influences the verdict.
