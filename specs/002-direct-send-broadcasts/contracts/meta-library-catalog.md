# Contract — Meta Library Catalog GET (consumed by Retail)

**Feature**: `002-direct-send-broadcasts`
**Consumer**: `retail-setup` — `MetaClient.fetch_library_template_by_name_and_language`
(new), called from `MetaService.fetch_library_template_by_name_and_language`.
**Producer**: Meta Cloud API — `GET {WHATSAPP_API_URL}/{META_VERSION}/message_template_library/`.
**Auth**: `Authorization: Bearer {settings.META_SYSTEM_USER_ACCESS_TOKEN}`.

This is the upstream HTTP contract Retail relies on to materialize
OrderStatus templates locally at agent-assignment time when the
WhatsApp channel has Direct Send enabled (FR-003a, FR-003c, FR-003d).

The same endpoint is already consumed today by
`MetaClient.get_pre_approved_template`; this contract documents the
**exact-name match** semantics required by the Direct Send path.

---

## 1. Request

```http
GET /{META_VERSION}/message_template_library/?search={template_name}&language={language} HTTP/1.1
Host: graph.facebook.com
Authorization: Bearer {META_SYSTEM_USER_ACCESS_TOKEN}
Content-Type: application/json
```

| Field            | Type   | Notes                                                                          |
| ---------------- | ------ | ------------------------------------------------------------------------------ |
| `template_name`  | string | The local `Template.name` (which equals `PreApprovedTemplate.name`).            |
| `language`       | string | Meta-format locale, e.g. `pt_BR`, `es_MX`, `en_US`.                             |
| `META_VERSION`   | string | Read from `settings.META_VERSION` (already configured for the legacy caller).  |

The `search` parameter is a fuzzy match on Meta's side — the response
may include items whose name only partially matches. The Retail
client MUST therefore filter the response to the exact-name match
(see §3).

---

## 2. Successful response

HTTP 200 with body:

```jsonc
{
  "data": [
    {
      "name":     "weni_order_shipped",
      "language": "pt_BR",
      "category": "UTILITY",
      "body":     "Olá {{1}}, seu pedido {{2}} foi enviado.",
      "body_params": ["customer_name", "order_id"],
      "footer":   "Equipe Loja XYZ",
      "header":   { "type": "TEXT", "text": "Pedido enviado" },     // OR { "type": "IMAGE", "example": "..." }
      "buttons":  [
        { "type": "URL",         "text": "Acompanhar pedido", "url": "https://loja.com/track/{{1}}" },
        { "type": "QUICK_REPLY", "text": "Não recebi" }
      ]
    }
    /* possibly more items (fuzzy search) */
  ],
  "paging": { "cursors": { "before": "...", "after": "..." } }
}
```

The fields `body`, `body_params`, `footer`, `header`, `buttons` are
the same keys already extracted by
`ValidatePreApprovedTemplatesUseCase._get_template_info` and
adapted by `TemplateTranslationAdapter` into the local
`Template.metadata` shape.

---

## 3. Retail-side post-filter (exact match)

The new client method MUST select **the first item** in `data` whose
`name == template_name` (the exact requested name, case-sensitive)
**AND** whose `language == language` (when present in the response).
If no item matches, the method returns `None`.

This guards against:

- Fuzzy-search false positives (a customer template named
  `weni_order_shipped_v2` showing up when searching for
  `weni_order_shipped`).
- Cross-language pollution (Meta returning a `pt_BR` template when
  `es_MX` was requested but missing).

---

## 4. Failure modes

| Mode                                          | HTTP            | Retail-side handling                                                                                                            |
| --------------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Template missing in the requested language    | 200 with empty `data` OR no exact-name match | Service returns `None`. Use case attempts the `pt_BR` fallback (FR-003c).                                                       |
| Template missing in `pt_BR` too (final retry) | 200 with empty `data` OR no exact-name match | Service returns `None`. Use case raises `DirectSendTemplateUnavailableError` → assignment rolls back (FR-003d).                  |
| Auth failure (403)                            | 4xx             | `MetaClient.make_request` raises; service catches, logs `error`, returns `None`. Use case follows the FR-003d path.              |
| Rate limit (429)                              | 4xx             | Same as auth failure (no retry policy in v1; Meta's library catalog is read at most once per template per assignment ATTEMPT — see §6 for the resolution of "operator can retry" vs. this policy).            |
| Meta server error (5xx)                       | 5xx             | Same as auth failure.                                                                                                          |
| Malformed JSON / unexpected schema            | 200             | Service catches the parsing exception, logs, returns `None`. Use case follows the FR-003d path.                                  |

The contract Retail honors is intentionally narrow:
**the service returns either a populated `dict` (the exact-name match)
or `None`**. Use cases never see HTTP details.

---

## 5. Validation rules applied at the service boundary

After extracting the matching item, the service MUST validate that
the components are within the Direct Send Beta v1 supported set
(Decision 12):

- `body` is a non-empty string.
- `header.type` ∈ {`TEXT`, `IMAGE`} (or absent).
- `buttons[*].type` ∈ {`URL`, `QUICK_REPLY`} (or absent).
- At most one `URL` button (Meta CTA limit).
- At most three `QUICK_REPLY` buttons (Meta reply-buttons limit).
- No `body`/`header`/`footer`/`button` text exceeds Meta's documented
  length limits (1024 / 60 / 60 / 20 chars respectively, before
  substitution).

Any violation MUST raise `DirectSendUnsupportedComponentError`,
which the use case translates into atomic assignment failure
(Decision 12, FR-003d).

---

## 6. Caching and partial-batch retries

**No Retail-side caching of catalog reads.** The library-catalog read
fires at most once per template per assignment attempt, and the
assignment is a low-frequency operator action. A cache layer would
only add a stale-read failure mode for no benefit.

**Partial-batch results are NOT cached across assignment attempts.**
`AssignAgentUseCase._create_library_templates` runs every Meta read
inside a single `@transaction.atomic` block (research Decision 5).
On FR-003d failure the transaction rolls back and ALL successful
fetches from that attempt are discarded. An operator-initiated retry
fires a NEW `AssignAgentUseCase.execute` with a fresh atomic block
that re-fetches every template from scratch.

This resolves the apparent conflict between the spec's "operator can
retry once Meta has the content (or recovers)" (spec Edge Cases /
FR-003d) and §4's "no retry policy in v1; library catalog is read at
most once per template per assignment":

- The unit "per assignment" means per-assignment-ATTEMPT.
- An operator retry is a new attempt with its own at-most-once
  reads of each template.
- Retail does not auto-retry, but Retail does not block the
  operator from doing so.

The contract guarantees the operator that a retry is always a
fresh, deterministic read; it does NOT promise the catalog state
will have changed in between.

---

## 7. Settings touched

| Setting                              | Used by                                                | Already configured? |
| ------------------------------------ | ------------------------------------------------------ | ------------------- |
| `WHATSAPP_API_URL`                   | base URL                                                | yes                 |
| `META_VERSION`                       | path version                                            | yes                 |
| `META_SYSTEM_USER_ACCESS_TOKEN`      | `Authorization` header                                  | yes                 |

No new environment variable is required for this feature.

---

## 8. Idempotency

GET — naturally idempotent. Each fetch is keyed by `(name, language)`
and returns the same response across reads (Meta's library catalog
content is updated by Meta, not by Retail). The Retail-side service
returns `None` deterministically for the same failure mode (e.g.
missing translation always produces `None`, regardless of how many
times the read is attempted within the same assignment attempt).
This deterministic-failure property is what makes the FR-003d atomic
rollback safe: every per-template fetch has a single, predictable
return shape regardless of when in the assignment attempt it fires.

---

## 9. Tenant isolation (spec FR-040, Multi-credential surface taxonomy)

The Meta library-catalog is a GLOBAL Meta-curated public resource
— there is no per-WABA, per-project, or per-tenant content in the
catalog. The endpoint returns the same templates to every consumer
regardless of which WABA the requesting account owns; Meta curates
the templates centrally and exposes them as a global catalog.

### 9.1 Single global system token (CROSS-TENANT credential by design)

Retail consumes the catalog using a SINGLE
`META_SYSTEM_USER_ACCESS_TOKEN` for ALL projects' library-catalog
reads. This is a CROSS-TENANT credential — it is the same token
regardless of which project's `AssignAgentUseCase.execute` is
running. The cross-tenant scope is acceptable because:

1. **The resource itself is cross-tenant**: there is no per-tenant
   data exposed by reads against the catalog. Two projects' fetches
   for the same `(name, language)` return byte-identical responses.
2. **No per-tenant Meta data is leaked back into Retail**: the
   response carries Meta-curated public template content (body,
   header, footer, buttons, language) — no `WABA_ID`,
   `PHONE_NUMBER_ID`, account name, or other per-tenant identifier
   appears in the response.

The taxonomy of Retail's four credential surfaces and which are
cross-tenant by design is documented in `spec.md` §Tenant isolation
("Multi-credential surface taxonomy") and `research.md` Decision 16.

### 9.2 Cross-tenant rate-limit blast radius (accepted trade-off)

A Meta-side rate-limit applied to `META_SYSTEM_USER_ACCESS_TOKEN`
reduces every project's library-catalog GET success rate at the
same time. Operator retries (per FR-003d) cannot independently
isolate one tenant from another at the credential level — a tenant
hitting Meta hard at agent assignment time can blow through the
shared rate-limit budget for every other tenant.

This is an accepted trade-off for v1, with three mitigating
properties:

- **Bounded surface**: library-catalog reads are
  agent-assignment-time-only. There is no dispatch-time dependency
  on the system token, so a rate-limit blocks NEW assignments but
  not existing tenants' broadcasts (the dispatch hot path uses
  per-channel WhatsApp Cloud credentials, which ARE per-tenant —
  see `contracts/messaging-gateway-payload.md` §1).
- **Low frequency**: agent assignment is an operator-initiated
  action, not a customer-event-driven one. Rate-limit consumption
  is bounded by the number of assignments per unit time.
- **Atomic-rollback on failure**: a 429 from Meta surfaces as
  `None` from `MetaService.fetch_library_template_by_name_and_language`
  (Section 4) and triggers FR-003d's atomic rollback; no partial
  state leaks across tenants.

The alternative (per-tenant Meta access tokens) requires
Beta-program-level cooperation from Meta to issue per-WABA
system-user tokens, plus a credential-management layer in Retail to
store and rotate them. Both are well outside the scope of this
feature. Documented as an Edge Case in `spec.md` ("Single Meta
system token rate-limit affects ALL projects' assignments
simultaneously") and as a `[Conflict]` resolution in `research.md`
Decision 16.

### 9.3 Audit trail records cross-tenant content source (spec data-model §3)

Every Direct Send-path Template carries
`metadata.direct_send.fetched_from_meta_library = true` together
with `requested_language`, `actual_language`, and `fetched_at`
(`data-model.md` §3). The boolean is the audit-trail proof that
the content originated from a CROSS-tenant Meta-curated public
resource — not from a per-tenant Meta WABA, not from another
project's local Template, not from operator input. A future audit
that needs to distinguish "per-tenant content" from "cross-tenant
content sources" can route on this flag without joining back to
the assignment use case.

### 9.4 Tenant boundary at assignment time

The atomic-rollback boundary at FR-003d is per-PROJECT: a failure
to fetch one of project A's required templates rolls back project
A's assignment ONLY. It does NOT affect any other project's
assignment, persisted Templates, or in-flight broadcasts. The
@transaction.atomic block scopes the rollback to a single
`AssignAgentUseCase.execute` invocation, which is itself scoped to
a single `(agent, project)` pair.
