# Contract — Messaging-Gateway Payload (Flows)

**Feature**: `002-direct-send-broadcasts`
**Producer**: `retail-setup` — `Broadcast.build_message` /
`Broadcast.build_direct_send_message` /
`Broadcast.build_broadcast_template_message`.
**Consumer**: Flows — `POST {FLOWS_REST_ENDPOINT}/api/v2/internals/whatsapp_broadcasts`.
**Wire format**: JSON.

This contract specifies the request body sent to Flows for both the
legacy and Direct Send dispatch paths. Story 4 (FR-015, SC-004)
mandates that the legacy shape stays bit-for-bit identical with
today; everything new is gated by the top-level boolean
`msg.direct_send`.

---

## 1. Common envelope

```jsonc
{
  "project": "<project_uuid>",
  "urns":    ["whatsapp:<E.164 number>"],
  "channel": "<channel_uuid>",
  "msg":     { ... }                        // shape depends on msg.direct_send
}
```

| Key       | Type     | Required | Notes                                                                     |
| --------- | -------- | -------- | ------------------------------------------------------------------------- |
| `project` | string   | yes      | UUID of the Retail `Project`. Unchanged from today.                        |
| `urns`    | string[] | yes      | Single-element list with the WhatsApp URN (e.g. `whatsapp:55981234567`).   |
| `channel` | string   | yes      | UUID of the WhatsApp Cloud channel that originated the broadcast. Unchanged. |
| `msg`     | object   | yes      | The message payload. See §2 (legacy) and §3 (Direct Send).                  |

---

## 2. Legacy path — `msg.direct_send` absent or `false`

Used when `IntegratedAgent.direct_send == False` (FR-015). The shape
is **exactly** what `Broadcast.build_broadcast_template_message`
emits today — no new keys, no removed keys.

### 2.1 `msg`

```jsonc
{
  "template": {
    "name":      "<Version.template_name>",   // required
    "locale":    "pt-BR",                     // optional, derived from data["language"] or template.metadata["language"]
    "variables": ["Maria", "12345"]           // optional, positional
  },
  "buttons":     [ /* see §2.2 */ ],          // optional
  "attachments": ["image/jpeg:<URL>"],        // optional, single element
  "interaction_type": "order_details",        // optional, only for in-chat payment flows
  "order_details":    { /* opaque to Retail */ }
}
```

### 2.2 Buttons (legacy)

```jsonc
[
  { "sub_type": "url",             "parameters": [{ "type": "text", "text": "<order_form_id>" }] },
  { "sub_type": "payment_request", "parameters": [{ "type": "<payment_type>", "text": "<payment_data>" }] }
]
```

| Key                          | Required | Notes                                                                              |
| ---------------------------- | -------- | ---------------------------------------------------------------------------------- |
| `sub_type`                   | yes      | Discriminator. Allowed: `"url"`, `"payment_request"`.                              |
| `parameters[0].type`         | yes      | For `url`: always `"text"`. For `payment_request`: payment system identifier.       |
| `parameters[0].text`         | yes      | Variable value to substitute on Meta's side (legacy substitution).                  |

### 2.3 Behavioural guarantees

- Meta performs the substitution; Flows passes through `template.name`
  + `template.locale` + `template.variables` + `buttons.parameters`.
- This shape is the **single source of truth** for Story 4: any byte
  difference in this section is a regression.

---

## 3. Direct Send path — `msg.direct_send: true`

Used when `IntegratedAgent.direct_send == True` (FR-014). Retail
performs the substitution server-side; Flows forwards the literal
message content to the Direct Send Beta endpoint.

### 3.1 `msg`

```jsonc
{
  "direct_send": true,                                      // required, exact value `true`
  "category":    "utility",                                 // required, exact value `"utility"`
  "template": {
    "name":   "<Version.template_name>",                    // required, used by Flows as direct_send_config.template_name
    "locale": "pt-BR"                                       // required, ISO-style locale (Meta-format with "_" → "-")
  },
  "body":   "Olá Maria, seu pedido 12345 foi enviado.",     // required, fully substituted body
  "header": { /* see §3.2 */ },                             // optional
  "footer": "Equipe Loja XYZ",                              // optional
  "interaction_type": "cta_url",                            // optional — see §3.3 (FR-014a)
  "cta_message": { /* see §3.3 */ },                        // optional — see §3.3 (FR-014a); siblings to interaction_type
  "quick_replies": [ /* see §3.3 */ ],                      // optional — see §3.3 (FR-014b); flat array of strings
  "attachments": ["image/jpeg:<URL>"]                       // optional, MUST appear when header.type == "image"
}
```

> **Direct Send NEVER emits `msg.buttons`** — the `buttons` key is
> LEGACY-ONLY on the wire (FR-014a(b) + FR-014b(b)). CTA URL and
> Quick Reply surfaces are emitted as top-level siblings on `msg`
> per FR-014a / FR-014b; see §3.3.

| Key                  | Required                              | Notes                                                                                       |
| -------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------- |
| `direct_send`        | yes                                   | Top-level routing signal (Decision 8). MUST be the literal `true`.                          |
| `category`           | yes                                   | MUST be `"utility"` per Direct Send Beta v1; non-utility is out of scope.                    |
| `template.name`      | yes                                   | The local `Version.template_name`. Validated against `^[a-z0-9_]+$`/512 chars before send.   |
| `template.locale`    | yes                                   | The actual language the substituted content is in (after any FR-003c fallback).              |
| `body`               | yes                                   | Final substituted body text (Retail-side substitution applied). Max 1024 chars (Meta limit). |
| `header`             | conditional — required when the template defines a header | See §3.2 for the discriminated-union shape.                              |
| `footer`             | optional                              | Final substituted footer text. Max 60 chars (Meta limit).                                    |
| `interaction_type`   | conditional — required when a CTA URL button is present | Spec FR-014a. Allowed value at v1: `"cta_url"`. Reserved spelling — `"interactive_type"` is INVALID. |
| `cta_message`        | conditional — required when `interaction_type == "cta_url"` | Spec FR-014a. See §3.3.                                              |
| `quick_replies`      | conditional — required when ≥1 QUICK_REPLY button is present | Spec FR-014b. JSON array of post-substitution title strings (no wrapping object). See §3.3. |
| `attachments`        | conditional — required when `header.type == "image"` | Same shape as legacy (`"image/<subtype>:<URL>"`).                                |

### 3.2 Header (Direct Send)

Discriminated union on `type`:

```jsonc
// Text header
{ "type": "text",  "text": "Pedido enviado" }

// Image header
{ "type": "image", "image_url": "https://cdn.loja.com/order_1234.jpg" }
```

| `type`  | Required keys           | Notes                                                                                |
| ------- | ----------------------- | ------------------------------------------------------------------------------------ |
| `text`  | `text`                  | Final substituted header text. Max 60 chars (Meta limit).                            |
| `image` | `image_url`             | Direct URL. Same value MUST also appear in `msg.attachments[0]` for downstream parity. |

### 3.3 CTA URL and Quick Replies (Direct Send)

> **Spec is canonical**: this section restates the wire shapes
> pinned by `spec.md` FR-014a and FR-014b. Earlier revisions of
> this contract (and the `direct_send_payload_builder` v1
> implementation) emitted CTA URL and Quick Replies as objects
> inside `msg.buttons` with `sub_type` discriminators
> (`{sub_type: "cta_url", display_text, url}` for CTA,
> `{sub_type: "reply", id, title}` for Quick Replies). Both shapes
> are documentation/implementation errors and are SUPERSEDED by
> FR-014a / FR-014b. The Direct Send path NEVER emits a
> `msg.buttons` key — `buttons` is LEGACY-ONLY (see §2.2 for the
> legacy-cohort shape).

#### 3.3.1 CTA URL — at most ONE per message (FR-014a)

The CTA URL surface is emitted as a top-level discriminator +
sibling sub-object on `msg`:

```jsonc
{
  "msg": {
    "direct_send": true,
    "category":    "utility",
    "template": { "name": "<template_name>", "locale": "<locale>" },
    "body":   "<substituted body>",
    "interaction_type": "cta_url",
    "cta_message": {
      "display_text": "Acompanhar pedido",
      "url":          "https://loja.com/track/12345"
    }
  }
}
```

| Key                          | Required keys                  | Notes                                                                                                |
| ---------------------------- | ------------------------------ | ---------------------------------------------------------------------------------------------------- |
| `msg.interaction_type`       | exact value `"cta_url"`        | FR-014a(a). Spelling `interactive_type` is INVALID.                                                  |
| `msg.cta_message.display_text` | yes                          | Final post-substitution button label. Max 20 chars (Meta limit; FR-014a(e)).                         |
| `msg.cta_message.url`        | yes                            | Final post-substitution URL (placeholders such as `{{1}}` substituted server-side per FR-013). The 20-char `MAX_BUTTON_LABEL_LENGTH` ceiling does NOT apply to `url` — Meta allows up to ~2000 chars. |

Cardinality: at most ONE `cta_message` per `msg` — structurally
guaranteed by FR-003f(d)'s ≤1 URL fetch-time count limit
(FR-014a(c)).

#### 3.3.2 Quick Replies — up to THREE per message (FR-014b)

Quick Reply surfaces are emitted as a top-level flat array of
post-substitution title strings on `msg`:

```jsonc
{
  "msg": {
    "direct_send": true,
    "category":    "utility",
    "template": { "name": "<template_name>", "locale": "<locale>" },
    "body":   "<substituted body>",
    "quick_replies": ["Sim", "Não", "Cancelar"]
  }
}
```

| Key                      | Required type           | Notes                                                                                                       |
| ------------------------ | ----------------------- | ----------------------------------------------------------------------------------------------------------- |
| `msg.quick_replies`      | `string[]` (1..3 items) | FR-014b(a). Each element is the post-substitution `title` of a `QUICK_REPLY` button from the catalog response. |

Cardinality: 1..3 entries per `msg` — structurally guaranteed by
FR-003f(d)'s ≤3 QUICK_REPLY fetch-time count limit (FR-014b(c)).

The Meta library catalog's `id` field (when present in the catalog
response) is intentionally NOT carried on the wire (FR-014b(a)).
Flows derives any downstream payload identifier from the title or
from its own per-channel handling against Meta's Direct Send Beta
endpoint.

#### 3.3.3 Combined case — URL + QUICK_REPLY in the same template

A template that carries BOTH a `URL` button AND `QUICK_REPLY`
buttons emits BOTH sets of keys as PARALLEL siblings on `msg`;
each surface is independent and neither suppresses the other
(FR-014b(f)):

```jsonc
{
  "msg": {
    "direct_send": true,
    "category":    "utility",
    "template": { "name": "<template_name>", "locale": "<locale>" },
    "body":   "<substituted body>",
    "interaction_type": "cta_url",
    "cta_message":  { "display_text": "Acompanhar pedido", "url": "https://loja.com/track/12345" },
    "quick_replies": ["Sim", "Não"]
  }
}
```

Upstream Direct Send Beta acceptance of the combined shape is a
Flows / Meta-side concern that the Retail spec does not enlarge —
if upstream rejects it, the broadcast settles as
`BroadcastMessage.status=FAILED` via the standard FR-035 flow.

### 3.4 Behavioural guarantees

- Retail does **all** variable substitution (FR-013). The keys
  `body`, `header.text`, `footer`, `cta_message.display_text`,
  `cta_message.url`, and each entry of `quick_replies[*]` are
  literal final strings — no `{{N}}` placeholders may appear.
- `template.variables` is intentionally absent in this shape —
  sending it would be ambiguous (Decision 8). The legacy
  `buttons[*].parameters` field is also absent because
  `msg.buttons` is LEGACY-ONLY on the wire (FR-014a(b) +
  FR-014b(b)).
- `template.name` MUST satisfy `^[a-z0-9_]+$` and length ≤ 512.
  If it doesn't, the broadcast is **not sent** at all and an audit
  log entry records the skip (Decision 7).

### 3.5 Spec is canonical

This contract restates the spec-level FR-014a / FR-014b shapes
for reviewer convenience and so the Flows-side consumer can wire
against the wire-shape without cross-referencing `spec.md`. If
this contract and `spec.md` ever disagree, the spec wins. This
mirrors the precedent established by FR-003e for the `header`
shape correction.

---

## 4. Validation summary (producer-side)

`Broadcast.build_direct_send_message` MUST refuse to emit a payload
when any of the following hold (returning `None` and emitting an
audit log entry, mirroring the existing "template not found" path):

1. `Version.template_name` violates `^[a-z0-9_]+$` or is longer than
   512 characters (Decision 7, FR-017).
2. `template.metadata["body"]` is missing or empty (FR — Direct Send
   beta requires a body component; pre-existing constraint restated
   in spec edge cases).
3. The substituted body, header, footer, `cta_message.display_text`,
   or any `quick_replies[*]` entry produced through variable
   substitution would exceed Meta's per-component length limits —
   body ≤ `MAX_BODY_LENGTH` (1024), header.text ≤
   `MAX_HEADER_TEXT_LENGTH` (60), footer ≤ `MAX_FOOTER_LENGTH` (60),
   `cta_message.display_text` ≤ `MAX_BUTTON_LABEL_LENGTH` (20),
   each `quick_replies[*]` ≤ `MAX_BUTTON_LABEL_LENGTH` (20). The
   `cta_message.url` field is NOT length-checked at this gate
   (FR-014a(e)). Decision 6 logs a warning but still emits; the
   absolute length limits are enforced here as a defensive last
   check before sending to Flows.

In every case the existing `BroadcastMessage` row is NOT persisted
(matching the legacy "template not found" semantics — see Story 1
spec text).

---

## 5. Examples

### 5.1 Direct Send — body + CTA URL + image header (FR-014a)

```jsonc
{
  "project": "9c2a1f3a-7b3a-4d61-9f17-fe4b2c2a1f3a",
  "urns":    ["whatsapp:5598123456789"],
  "channel": "1f3a9c2a-fe4b-4d61-9f17-7b3a4d619f17",
  "msg": {
    "direct_send": true,
    "category":    "utility",
    "template": {
      "name":   "weni_order_shipped_1700000000",
      "locale": "pt-BR"
    },
    "body":   "Olá Maria, seu pedido 12345 foi enviado e chegará em 3 dias úteis.",
    "header": { "type": "image", "image_url": "https://cdn.loja.com/order_12345.jpg" },
    "footer": "Equipe Loja XYZ",
    "interaction_type": "cta_url",
    "cta_message": {
      "display_text": "Acompanhar pedido",
      "url":          "https://loja.com/track/12345"
    },
    "attachments": ["image/jpeg:https://cdn.loja.com/order_12345.jpg"]
  }
}
```

> **Note**: `msg.buttons` is intentionally absent on the Direct
> Send path (FR-014a(b)). The CTA URL surface lives on
> `msg.interaction_type` + `msg.cta_message`.

### 5.1b Direct Send — body + Quick Replies (FR-014b)

```jsonc
{
  "project": "9c2a1f3a-7b3a-4d61-9f17-fe4b2c2a1f3a",
  "urns":    ["whatsapp:5598123456789"],
  "channel": "1f3a9c2a-fe4b-4d61-9f17-7b3a4d619f17",
  "msg": {
    "direct_send": true,
    "category":    "utility",
    "template": {
      "name":   "order_canceled_3",
      "locale": "pt-BR"
    },
    "body":   "Olá Maria, seu pedido 12345 foi cancelado. Você gostaria de…",
    "quick_replies": ["Sim", "Não", "Detalhes do pedido"]
  }
}
```

### 5.1c Direct Send — body + CTA URL + Quick Replies (combined case)

```jsonc
{
  "project": "9c2a1f3a-7b3a-4d61-9f17-fe4b2c2a1f3a",
  "urns":    ["whatsapp:5598123456789"],
  "channel": "1f3a9c2a-fe4b-4d61-9f17-7b3a4d619f17",
  "msg": {
    "direct_send": true,
    "category":    "utility",
    "template": {
      "name":   "weni_order_invoiced_1700000000",
      "locale": "pt-BR"
    },
    "body":   "Olá Maria, sua nota fiscal do pedido 12345 foi emitida.",
    "interaction_type": "cta_url",
    "cta_message":  { "display_text": "Acompanhar pedido", "url": "https://loja.com/track/12345" },
    "quick_replies": ["Sim", "Não"]
  }
}
```

### 5.2 Direct Send — body only (no header, no footer, no buttons)

```jsonc
{
  "project": "9c2a1f3a-7b3a-4d61-9f17-fe4b2c2a1f3a",
  "urns":    ["whatsapp:5598123456789"],
  "channel": "1f3a9c2a-fe4b-4d61-9f17-7b3a4d619f17",
  "msg": {
    "direct_send": true,
    "category":    "utility",
    "template": {
      "name":   "weni_order_invoiced_1700000000",
      "locale": "pt-BR"
    },
    "body": "Olá Maria, sua nota fiscal do pedido 12345 foi emitida."
  }
}
```

### 5.3 Legacy — same OrderStatus event, Direct Send disabled

```jsonc
{
  "project": "9c2a1f3a-7b3a-4d61-9f17-fe4b2c2a1f3a",
  "urns":    ["whatsapp:5598123456789"],
  "channel": "1f3a9c2a-fe4b-4d61-9f17-7b3a4d619f17",
  "msg": {
    "template": {
      "name":      "weni_order_shipped_1700000000",
      "locale":    "pt-BR",
      "variables": ["Maria", "12345"]
    },
    "buttons": [
      { "sub_type": "url", "parameters": [{ "type": "text", "text": "12345" }] }
    ],
    "attachments": ["image/jpeg:https://cdn.loja.com/order_12345.jpg"]
  }
}
```

---

## 6. Versioning

This contract is versioned by the existence (or absence) of
`msg.direct_send`. No HTTP version header changes. Future Direct
Send shape extensions (e.g. `ttl_seconds` per Direct Send Beta v3)
are added as new optional keys under `msg`; existing keys never
change semantics.

---

## 7. Idempotency (Retail ↔ Flows boundary)

This section pins the idempotency expectations on the Retail-to-Flows
boundary, supporting spec FR-028 through FR-039 and the
**Exactly-Once Dispatch** named invariant.

### 7.1 Retry budget — Retail side

Retail does NOT retry this POST on its own. The dispatch use case
(`Broadcast.send_message`) issues exactly one HTTP request per
admitted order-status event; on any 4xx / 5xx / network error the
caller records a FAILED `BroadcastMessage` via
`_record_failed_dispatch` and re-raises. There is no in-process
retry loop, no Celery requeue, and no exponential-backoff on this
boundary.

The implication: Flows MUST treat each request as a one-shot
delivery attempt. Whatever recovery Flows performs on its side
(retry to Meta, dead-letter handling) is opaque to Retail.

### 7.2 Idempotency on the same `(project, urns, msg)` payload

Retail does NOT rely on Flows being idempotent on a re-submitted
payload. Two POSTs with identical bodies — should one ever occur —
will be treated by Retail as two distinct dispatches; the
`BroadcastMessage` rows persisted from the two responses will hold
distinct `broadcast_id` values (each Flows response is independent).

The trigger-side dedup at the order-status webhook
(`AgentOrderStatusUpdateUsecase._is_duplicate_event`, spec FR-028)
is the mechanism that prevents this from happening in production —
duplicate webhooks are filtered before the Flows POST is ever
issued.

### 7.3 `broadcast_id` allocation and uniqueness

Flows is the authority on `broadcast_id` and Retail relies on three
properties:

1. **Global uniqueness across all Weni tenants** — the same
   `broadcast_id` MUST NOT be issued for two distinct broadcasts in
   any project. This is the precondition that makes
   `HandleStatusUpdateUseCase._link_message_to_broadcast`'s
   project-less lookup by `broadcast_id` safe.
2. **Stability** — once issued in a successful response,
   `broadcast_id` MUST be the canonical identifier for every
   subsequent EDA event on `retail.template-send` and
   `retail.template-status` for that broadcast.
3. **One-shot allocation** — Flows MUST NOT issue a new
   `broadcast_id` for a re-delivered Retail POST that hits the same
   logical broadcast on the Flows side. Conversely, Retail does not
   re-deliver POSTs (see §7.1).

Persistence-side dedup on the Retail side is enforced by the
`broadcasts_broadcast_id_unique` conditional unique constraint
(`retail/broadcasts/models.py:145-150`); a `broadcast_id` collision
across two projects would manifest as an `IntegrityError` at insert
time. Spec FR-032 restates the constraint as a normative
requirement.

### 7.4 `external_message_id` (Meta-side identifier)

Flows obtains `external_message_id` from Meta upon successful
hand-off and emits it on the first `retail.template-send` event.
Retail uses it (together with `broadcast_id` on the first event,
and on its own afterwards) to apply status transitions.

Retail's persistence-side dedup on this field is enforced by
`broadcasts_external_message_id_unique` (conditional unique
constraint, also restated by FR-032).

### 7.5 Status-callback replay

If Flows replays the same status event (e.g. a `delivered` event
with the same `external_message_id`), Retail handles it via the
lifecycle-rank guard in `_apply_status_transition`
(`retail/broadcasts/usecases/handle_status_update.py:190-256`,
spec FR-035): a status equal to or earlier than the row's current
status is ignored as `status_out_of_order_ignored`. The first
DELIVERED transition is the only one that increments the
`broadcasts_delivered` counter (spec FR-034).

### 7.6 Direct Send-specific identifier collisions

Spec Edge Cases reference Meta error code 132021 (Direct Send
template-name collision in the same WABA). When this error reaches
Retail asynchronously via the status callback, Retail records the
upstream code on `BroadcastMessage.last_payload` and transitions
`status` to FAILED. There is no Retail-side compensation. The
operator-facing recovery is to rename the local Template and
re-assign (see spec Edge Cases).

---

## 8. Tenant isolation (spec FR-040, FR-041, FR-042)

This section pins the tenant-isolation expectations on the
Retail-to-Flows boundary, supporting spec FR-040 / FR-041 / FR-042
and the **Tenant Isolation** named invariant.

### 8.1 Per-tenant credentials at dispatch (in contrast with assignment time)

Direct Send DISPATCH (POST to Flows → POST to
`<PHONE_NUMBER_ID>/messages` on Meta's side) uses the project's
PER-TENANT WhatsApp Cloud channel credentials, NOT the
cross-tenant `META_SYSTEM_USER_ACCESS_TOKEN` consumed at
agent-assignment time (`contracts/meta-library-catalog.md` §9).
This is the per-tenant boundary at dispatch time:

- The `channel` UUID in the request body (Section 1) identifies
  the project's WhatsApp Cloud channel.
- Flows resolves the channel's WABA / phone-number / access-token
  triplet from its own per-channel credential store.
- The Meta-side dispatch token is per-WABA — i.e. per-project at
  v1, since each project has its own WABA.
- Retail does NOT hold the per-channel credentials directly; the
  separation of concerns is intentional (Integrations Engine and
  Flows are the keepers of per-channel state).

The Flows internal-auth token used on the Retail → Flows leg
itself is a CROSS-tenant Weni service-account token (see spec.md
§Tenant isolation, Multi-credential surface taxonomy); tenant
scoping on the Flows side is enforced via the request body's
`project` field, not via the auth token.

### 8.2 Required `project` field

The top-level `project` field (Section 1) MUST be set to
`str(integrated_agent.project.uuid)` — the canonical tenant
identifier (spec FR-040, FR-042). This field is the
authoritative tenant tag for downstream consumers (Flows-side
audit, datalake aggregation, courier topic routing).

A future change that drops the `project` field, replaces it with
a non-globally-unique identifier (e.g. `agent_uuid` alone), or
populates it from a value other than `integrated_agent.project.uuid`
is a forbidden tenant-isolation regression.

### 8.3 Inbound EDA event tenant resolution

Status-callback events (`retail.template-send`,
`retail.template-status`) consumed by `BroadcastConsumer` resolve
the target tenant via two mechanisms — both safe under the
upstream contracts pinned in §7:

| First event class                                  | Lookup key             | Tenant safety property                                                                                       |
| -------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------ |
| First `retail.template-send` event for a broadcast | `broadcast_id`         | Flows-side global uniqueness across all Weni tenants (§7.3) — `broadcast_id` resolves to exactly one row.    |
| Subsequent `retail.template-status` events         | `external_message_id`  | Meta-side global uniqueness on `wamid` — `external_message_id` resolves to exactly one row.                  |

Both lookups bypass the project filter in the queryset because the
lookup keys are themselves globally unique; the matched row's
`project_id` is the canonical tenant for any subsequent write
(`retail/broadcasts/usecases/handle_status_update.py`). When an
event payload carries a `project` field that disagrees with the
matched row's `project_id`, the matched row's tenant is
authoritative — the disagreement is logged at WARNING per spec
FR-041.

The `broadcasts_broadcast_id_unique` and
`broadcasts_external_message_id_unique` conditional unique
constraints (FR-032) are the structural guard against a Flows-side
or Meta-side cross-tenant identifier misroute: a duplicate identifier
across two tenants raises `IntegrityError` at insert time rather
than silently writing into the wrong row.

### 8.4 Datalake event tenant tagging

Outbound datalake events emitted at the same dispatch boundary
(`weni_datalake_sdk` / `CommerceWebhookPath`,
`Broadcast._send_to_datalake` at
`retail/agents/domains/agent_webhook/services/broadcast.py:743-754`)
MUST include `project=str(integrated_agent.project.uuid)` as a
top-level field (FR-042). Spec FR-042 forbids any future emission
that drops or replaces the field; the legacy datalake snapshot
test (`tasks.md` T035a) pins the field's presence.
