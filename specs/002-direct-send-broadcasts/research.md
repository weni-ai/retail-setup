# Phase 0 Research: WhatsApp Direct Send Broadcasts (OrderStatus)

**Feature**: `002-direct-send-broadcasts`
**Date**: 2026-05-20
**Spec**: `./spec.md`

This document records the design decisions taken to remove every
`NEEDS CLARIFICATION` from the plan and the alternatives we rejected
on the way. Every decision is sized so a single PR can implement it
without reopening this file.

---

## Decision 1 — Where the per-IntegratedAgent Direct Send flag lives

> **⚠️ SUPERSEDED by `data-model.md §1` (spec correction).** The
> Direct Send flag is stored as an optional key (`direct_send: bool`)
> inside the existing `IntegratedAgent.config` JSONField, **not** as a
> new boolean column on `IntegratedAgent`. Absence of the key is
> interpreted as `False`. Reads MUST use
> `obj.config.get("direct_send", False)`; writes use
> `agent.config["direct_send"] = ...; agent.save(update_fields=["config"])`.
> See `data-model.md §1` for the canonical rationale (zero schema
> change on `IntegratedAgent`; trivially provable byte-identical
> legacy-path guarantee; smallest possible additive change). The text
> below records the original column-approach reasoning for historical
> auditability only — do not implement against it. Decision 13 below
> is also superseded by the same data-model.md §1 entry (no migration
> ships against the agents app).

**Original decision (HISTORICAL)**: Add a dedicated boolean column `direct_send` on
`IntegratedAgent` (default `False`).

**Original rationale (HISTORICAL)**:

- The flag is read on the broadcast hot path (every order-status event
  dispatches one DB hit on `IntegratedAgent` to get the templates and
  channel; reading a column is free, reading a JSON key requires a
  JSON traversal in Python and risks typo/key-shape drift).
- A column makes the flag indexable / queryable for ops dashboards
  and analytics (e.g. "how many projects are on Direct Send today").
- The constitution allows new columns on legacy models without forcing
  a PK migration; only *new models* must adopt the integer-PK +
  `uuid (unique=True)` pattern. `IntegratedAgent` keeps its existing
  UUID PK.
- Aligns with the existing pattern of typed scalar fields on the
  model (`is_active`, `contact_percentage`, `broadcasts_delivered`).
  `config` JSONField stays for runtime settings (cooldowns, locale,
  payment-recovery sub-config, …) — it is not the right home for a
  feature-routing flag.

**Alternatives considered (HISTORICAL)**:

- *Stash the flag in `IntegratedAgent.config["direct_send"]`*: this
  is the alternative that was **ultimately adopted** by the spec
  correction documented in `data-model.md §1`. The original objections
  (extra `config.get` per read, serializer fallback, typo class) are
  outweighed by the zero-schema-change benefit and the trivially
  provable byte-identical legacy-path guarantee — the cost calculus
  reversed once Story 4's snapshot tests made the legacy-cohort
  preservation gate explicit.
- *Move the flag to `Project`*: rejected because the spec is explicit
  that the flag is a snapshot taken at agent-assignment time and must
  not auto-resync if the WhatsApp channel later changes; tying it to
  the `Project` would imply "auto-resync on next read", which the
  spec rules out.
- *A separate `IntegratedAgentSettings` table*: rejected for one
  boolean — premature normalization and one extra join per dispatch.

---

## Decision 2 — How to identify the OrderStatus agent for the
"only OrderStatus is eligible" guard (FR-019)

**Decision**: Reuse the existing `settings.ORDER_STATUS_AGENT_UUID`
environment variable, the same one the order-status webhook flow
already uses (`retail/agents/domains/agent_webhook/usecases/order_status.py:101`).

**Rationale**:

- The setting is already wired (`retail/settings.py:332`) and is the
  team's canonical OrderStatus selector.
- It mirrors the established pattern of `ABANDONED_CART_AGENT_UUID`
  and `PAYMENT_RECOVERY_AGENT_UUID` used in `assign.py:172-189`.
- A single source of truth avoids drift between the
  assignment-time eligibility check and the webhook-time agent lookup.

**Alternatives considered**:

- *Identify by `Agent.slug` (e.g. `"order_status"`)*: rejected because
  slugs are per-customer (`Agent.objects.update_or_create(slug=..., project=...)`),
  so there is no global `slug == "order_status"` invariant. The UUID
  is the only stable identifier across customer pushes.
- *Add a per-agent `is_direct_send_eligible` boolean*: defers the
  decision to data setup; rejected because the spec is already
  explicit that *only* OrderStatus is eligible at v1, and that
  expansion is "a future feature".

---

## Decision 3 — How to read the channel's Direct Send flag

**Decision**: Reuse the existing
`IntegrationsService.get_channel_app(apptype="wpp-cloud", app_uuid=app_uuid)`
helper (`retail/services/integrations/service.py:372`) and read the
flag from the response's `config.direct_send` boolean.

If the call returns `None` (the existing service contract on any HTTP
error) or the response has no `config.direct_send` key, default to
`False` and emit a `logger.warning` capturing
`(app_uuid, project_uuid, agent_uuid, reason)` so operators can spot
the silent fallback.

**Rationale**:

- `IntegrationsService.get_channel_app` already has the right
  contract: it catches `CustomAPIException`, logs, and returns
  `None`, so the assignment use case never has to reach for a `try`
  block of its own (matches Constitution Principle I — Services
  swallow infrastructure errors and return `None`).
- The "default to disabled on lookup failure" behavior is the
  conservative one mandated by FR-005 and User Story 2 scenario 3.
- Reading from `response["config"]["direct_send"]` follows the same
  shape used today for `response["config"]["script"]` in
  `retail/api/onboard/usecases/publish_webchat_script.py` — keeping
  the shape conventional makes the Integrations team's contract
  obvious.

**Alternatives considered**:

- *Add a dedicated `IntegrationsService.get_wpp_cloud_direct_send_flag(app_uuid)`
  helper*: clearer but a single-purpose wrapper for what is one
  field read; rejected as premature abstraction. We add a tiny
  helper inside the assignment use case instead.
- *Persist the channel's Direct Send flag on the `Project`*: would
  require a sync mechanism; out of scope (assumption already in spec).

---

## Decision 4 — Where to fetch OrderStatus template content from Meta

**Decision**: Add a new service method
`MetaService.fetch_library_template_by_name_and_language(name, language) -> Optional[dict]`
backed by a new client method
`MetaClient.fetch_library_template_by_name_and_language(name, language)`
that calls `GET {settings.META_API_URL}/message_template_library/?search={name}&language={language}`
(where `settings.META_API_URL == urljoin(env.str("WHATSAPP_API_URL"), env.str("META_VERSION"))`)
and returns the first response item whose `name == name` (exact match
on the library-catalog response). The method returns `None` when:

- the HTTP call fails (Service swallows the error, logs `error`,
  returns `None`).
- `data` is empty.
- no item in `data` has `name == name`.

The use case layer interprets `None` as "not available in this language"
and triggers the `pt_BR` fallback (FR-003c).

**Rationale**:

- The existing `MetaService.get_pre_approved_template(name, language)`
  is already a library-catalog GET, so we are adding a thin
  exact-match wrapper, not a new infra dependency.
- We **do not** rename `get_pre_approved_template` because it has an
  active caller (`ValidatePreApprovedTemplatesUseCase` at push-time)
  whose semantics expect the existing fuzzy-search behavior; renaming
  would force a refactor outside this feature's scope.
- A dedicated method lets us share the body of the "find exact match
  in library catalog" logic across the Direct-Send-assignment use
  case and any future reuse without leaking implementation details to
  the use case.
- The exact-name match is required because Meta's
  `?search=` is a fuzzy match; with the legacy push-time path we get
  away with `data[0]` because the search string is always the
  template's full canonical name, but for Direct Send we must
  guarantee no false positives.

**Cross-reference with Decision 9**: The push-time validation in
`ValidatePreApprovedTemplatesUseCase._get_template_info` keeps
calling `get_pre_approved_template` exactly as today. Decision 9's
helper split (pure adapter + Direct-Send-only fetcher) is what
makes this possible — only the response-shaping step is shared
between the two paths, NOT the HTTP call.

**Alternatives considered**:

- *Reuse `MetaService.get_pre_approved_template` and post-filter in
  the use case*: would duplicate the exact-match logic at every
  callsite; rejected.
- *Hit `GET /<WABA_ID>/message_templates?source=AUTO_GENERATED&name=...`*
  (the Direct-Send-specific endpoint): rejected because that endpoint
  returns auto-generated templates (the templates Meta creates
  reactively from message content), not the *library catalog* templates
  the OrderStatus agent is curated against. The spec is explicit:
  "fetch each template from Meta's library catalog". The library
  endpoint does not require a WABA id and uses a system token, which
  matches the auth currently configured for `MetaClient`.

---

## Decision 5 — `pt_BR` fallback behavior (FR-003c / FR-003d)

**Decision**: Per-template fallback chain inside the assignment use
case:

```text
for each PreApprovedTemplate of the OrderStatus agent:
  meta_template = meta_service.fetch_library_template_by_name_and_language(name, project_language)
  if meta_template is None and project_language != "pt_BR":
      meta_template = meta_service.fetch_library_template_by_name_and_language(name, "pt_BR")
      if meta_template is not None:
          logger.warning(
              f"[DirectSend] template_language_fallback: "
              f"agent={agent.uuid} template={name} "
              f"requested_language={project_language} fallback_language=pt_BR"
          )
          actual_language = "pt_BR"
      else:
          actual_language = None
  elif meta_template is not None:
      actual_language = project_language
  else:
      # project_language was already pt_BR and it failed
      actual_language = None

  if meta_template is None:
      raise DirectSendTemplateUnavailableError(
          template_name=name,
          requested_language=project_language,
          fallback_language="pt_BR",
      )

  persist_template(meta_template, language=actual_language, status="APPROVED")
```

The whole block runs inside the existing
`@transaction.atomic execute(...)` so any failure rolls back **every**
row (FR-003d, atomic assignment failure).

**Rationale**:

- The two-step language chain matches the clarification recorded in
  `spec.md` (Q3: project language → `pt_BR`). A per-template chain
  (instead of all-or-nothing per agent) lets a partial language gap
  in Meta's catalog still produce a usable assignment (the spec's
  Story 2 scenario 4 explicitly requires this).
- A single warning per fallback gives operators the signal they need
  ("this template will deliver in pt_BR even though the project is
  es_MX") without spamming logs.
- A custom exception with a descriptive name keeps the `transaction.atomic`
  boundary honest (the rollback trigger is unambiguous in the trace).
- Skipping the second fetch when `project_language == "pt_BR"` is the
  cheapest and clearest implementation; we don't issue a useless
  duplicate request.

**Alternatives considered**:

- *Atomic per-language ("either every template in pt-BR or every
  template in the project language, never mixed")*: rejected because
  the spec acceptance scenario allows mixed (Story 2 scenario 4).
- *Background retry / async re-fetch*: rejected because the assignment
  must succeed atomically before the operator sees a "ready" status;
  asynchronous retry is a different feature.

---

## Decision 6 — Variable substitution algorithm

**Decision**: Add a small substitution helper in
`retail/agents/domains/agent_webhook/services/variable_substitution.py`
(or, if simpler, as a private method on a new `DirectSendBroadcast`
class in the same `services/` package) that:

1. Takes a string `template` and a dict `variables: Dict[str | int, str]`.
2. Replaces every occurrence of `{{N}}` with `str(variables[str(N)])`.
3. When `N` is missing from `variables`: replaces with empty string
   AND logs `logger.warning(f"variable_missing: template_name={...} index={N}")`.
4. When `variables` carries indices that don't appear in the template:
   silently ignores them (the rule engine is allowed to over-supply).

The helper is called for every text-bearing component of the
substituted Direct Send payload:

- body text
- header text (when header type is `TEXT`)
- footer text (rare but allowed; no variables in OrderStatus
  templates today, but supported to remain forward-compatible)
- CTA URL button URL (when the URL contains `{{1}}`)
- Quick-reply button text (when the title contains `{{1}}`)

Header image and image URL are NOT substituted by this helper; they
are pulled from the rule engine's special key `image_url` (existing
contract from `Broadcast.build_broadcast_template_message`).

**Rationale**:

- The substitution is small, pure, side-effect-free, and used in
  exactly one place (`DirectSendBroadcast.build_message`); it does
  not deserve its own use case but it does deserve its own testable
  function — explicit input/output makes the spec's edge cases
  ("variable values missing", "variable values for indices that do
  not exist") trivial to test.
- Logging is at WARNING (not ERROR) per the spec edge case: the
  broadcast still proceeds, so this is a recoverable anomaly.
- The function name expresses intent without needing a comment
  (Constitution Principle IV).

**Alternatives considered**:

- *Use Python's `str.format` with positional args*: rejected because
  Meta's `{{1}}` placeholder syntax (double braces) is not the same
  as Python's `{0}`/`{}` and the conversion is brittle for missing
  indices.
- *Use a regex `re.sub({{(\d+)}}, ...)`*: this is exactly what the
  helper will use internally; "regex vs no-regex" is implementation
  detail, not architecture.

---

## Decision 7 — Direct Send identifier rule violation (FR-017 + edge case)

**Decision**: When a template's local `name` violates Meta's Direct
Send naming rule (regex `^[a-z0-9_]+$`, max 512 chars), the broadcast
is **skipped silently** with an audit log entry that includes the
template name, the failing rule, and the originating order-status
event. No normalization is attempted at this layer.

The audit log shape is disjoint from both (a) the existing
skip-on-non-APPROVED log line (preserved bit-for-bit per FR-027)
and (b) the new `[BroadcastDispatch] skipped_due_to_status: ...`
shape introduced for `PAUSED` / `FLAGGED`. The Direct-Send-specific
refusals share a single dedicated shape — `[BroadcastDispatch]
skipped_due_to_direct_send_validation: agent={...} template={...}
reason={naming_rule|empty_body|component_length_limit} event={data}`
— so log consumers can route on each refusal class independently
(pinned by `tasks.md` T013).

**Rationale**:

- The OrderStatus agent's templates are assigned through the
  pre-approved-template flow, whose names are already snake_case
  (`weni_<purpose>_<timestamp>`). The spec's Assumptions block
  ("the OrderStatus agent's templates ... are already named in the
  lowercase-alphanumeric-with-underscores pattern") guarantees no
  name ever fails this validation today.
- Normalizing on the way out (e.g. lowercasing, replacing dashes
  with underscores) would silently change the Direct Send identifier
  Meta receives, which de-syncs Retail's local Template name from
  Meta's auto-created template name and breaks the FAQ rule
  "non-Direct-Send templates can't be used to send Direct Send
  messages". A skip is the safer default.
- A skip-with-audit-log matches the existing model for "broadcast
  not dispatchable for a structural reason" (the same model used
  for non-APPROVED versions in Story 3).

**Alternatives considered**:

- *Normalize on the way out*: rejected for the consistency reason
  above.
- *Reject the assignment if any template name is invalid*: too
  punitive (the cohort it would protect is empty today).
- *Auto-rename the template at assignment time*: changes the local
  Template name, which would diverge from how the legacy path
  stores it; rejected.

---

## Decision 8 — Direct Send payload shape sent to the messaging gateway

**⚠️ SUPERSEDED in part by spec FR-014c / FR-014d (Session 2026-05-22 Q14–Q18) and `tasks.md` Phase 8 second extension / T116 / T117 / T118.** Original Decision 8 points 2, 6, and 7 below describe the pre-FR-014c / pre-FR-014d wire shape (substituted body emitted as `msg.body`; local template name nested under `msg.template.name`; locale carried on `msg.template.locale`). The canonical Direct Send wire shape now drops `msg.template` entirely (FR-014c(a)), emits the local template name on the top-level sibling key `msg.direct_send_template_name` (FR-014c(g)), drops locale from the wire entirely (FR-014c(f) — no `msg.locale` / `msg.language` / `msg.template.locale`), and renames the substituted body wire key from `msg.body` to `msg.text` (FR-014d). FR-014c is a structural relocation; FR-014d is a wire-only rename (the internal storage key `Template.metadata["body"]`, the `MAX_BODY_LENGTH` constant, and the FR-039 audit-log discriminator `reason=empty_body` are preserved unchanged per FR-014d(c)). The original wording is preserved verbatim below for git-history continuity; the canonical shape lives on `spec.md` FR-014c / FR-014d and is restated in `contracts/messaging-gateway-payload.md` §3.1 / §3.4 / §5.x (corrected by `tasks.md` T118).

**Decision**: Extend the existing Flows broadcast payload by:

1. Adding a top-level boolean `msg.direct_send: true`.
2. Adding `msg.body: "<final substituted body text>"` (literal
   substituted body). **⚠️ SUPERSEDED by FR-014d** — the canonical wire
   key is now `msg.text`; see the SUPERSEDED block above for the full
   rationale.
3. Adding `msg.header: {type: "text"|"image", text: "...", image_url: "..."}`
   when the template has a header (text or image, with substitution
   applied to text headers).
4. Adding `msg.footer: "<literal footer text>"` when the template
   has a footer.
5. **⚠️ SUPERSEDED by spec FR-014a / FR-014b (Session 2026-05-22 Q4 / Q10) and `tasks.md` Phase 8 / T113 / T114.** Original Decision 8 wording: "Replacing `msg.buttons[i].parameters[0].text` payload semantics with the literal final values: `{sub_type: "cta_url", display_text, url}` for CTA URL, `{sub_type: "reply", id, title}` for quick replies." The canonical wire shape on the Direct Send path is now: CTA URL → top-level `msg.interaction_type = "cta_url"` + `msg.cta_message = {display_text, url}` (FR-014a); QUICK_REPLY → top-level flat array `msg.quick_replies = ["title 1", ...]` (FR-014b); the Direct Send path NEVER emits a `msg.buttons` key — `msg.buttons` is LEGACY-ONLY (the legacy cohort keeps emitting `{sub_type: "url", parameters: [...]}` and `{sub_type: "payment_request", parameters: [...]}` per FR-020 byte-identical preservation, but this is on a different code path that does NOT exercise this Decision). The original wording is preserved verbatim above for git-history continuity; the canonical shape lives on `spec.md` FR-014a / FR-014b and is restated in `contracts/messaging-gateway-payload.md` §3.3 (corrected by `tasks.md` T115).
6. **⚠️ SUPERSEDED by FR-014c** — Removing `msg.template.variables`
   entirely from the Direct Send shape — Retail does the substitution,
   so Flows doesn't need them. The canonical wire shape drops the
   entire `msg.template` block (FR-014c(a)), so the "removing
   variables" point is structurally subsumed.
7. **⚠️ SUPERSEDED by FR-014c** — Keeping `msg.template.name` and
   `msg.template.locale` because Flows uses them as the Direct Send
   `direct_send_config.template_name` and as the WhatsApp message
   language tag. The canonical wire shape now emits the local template
   name on `msg.direct_send_template_name` (FR-014c(g)) and computes
   locale internally without emitting it on the wire (FR-014c(f));
   Flows resolves the language internally from the channel's stored
   credentials.

The legacy payload shape (template name + locale + positional
variables, with components passed via `buttons` / `attachments` /
`order_details`) is preserved bit-for-bit when `IntegratedAgent.direct_send`
is `False` (FR-015, SC-004).

**Rationale**:

- Flows is internal to Weni; the team owns both ends, so we are
  free to design the cleanest shape.
- A single boolean (`msg.direct_send`) lets Flows route at the
  top level — no shape detection required. This is the minimum
  signal the spec demands ("with the Direct Send flag set").
- **⚠️ Historical note — superseded by FR-014c** — Keeping
  `msg.template.name` was originally required as the Direct Send
  identifier carried to Meta. Folded by FR-014c: the local template
  name is now emitted on the top-level sibling key
  `msg.direct_send_template_name`; the canonical Direct Send
  `direct_send_config.template_name` is sourced by Flows from that
  key.
- **⚠️ Historical note — superseded in part by FR-014d** — Putting
  the literal substituted content in dedicated keys (originally
  `msg.body`, `msg.header`, `msg.footer`) — instead of jamming it
  back into the legacy `msg.template.variables` — keeps the legacy
  payload untouched (zero risk for the regression Story 4 protects
  against) and makes the new path self-describing. FR-014d renames
  the wire body key from `msg.body` to `msg.text` (wire-only —
  internal storage `Template.metadata["body"]` is preserved per
  FR-014d(c)); the header / footer sibling keys are unchanged.
- The image header continues to be carried via the existing
  `msg.attachments[0]` mechanism for Direct Send too — the rule
  engine returns an `image_url` and the existing builder logic
  already converts that to `"image/png:<url>"`. We DO NOT
  introduce a parallel serialization for the same content.
- Buttons keep the `sub_type` key (`url`, `payment_request`,
  `reply`) so Flows can route consistently across legacy and
  Direct Send. The CTA URL button just carries a final
  substituted URL instead of a template-variable parameter.

**Alternatives considered**:

- *Send a completely separate top-level field (e.g. `direct_send_msg`)
  alongside `msg`*: rejected because it doubles the wire shape and
  forces every consumer to know both. A single `msg` with a flag is
  cleaner.
- *Inline the WhatsApp Cloud API payload exactly as Meta expects it
  (the `interactive`/`text` discriminated-union shape)*: rejected
  because that's Flows' responsibility (Flows is the gateway and
  knows its outbound contract). Retail's job is to send Flows enough
  context to build the Meta payload, not the Meta payload itself.
- *Reuse `msg.template.variables` to carry final substituted values
  in order*: rejected because it overloads a field whose name
  documents itself as "variables to substitute"; future readers
  would assume Flows does the substitution.

The final shape is documented in `./contracts/messaging-gateway-payload.md`.

---

## Decision 9 — Template content extraction at assignment time

**Decision**: Split the shared logic into TWO layers in
`retail/templates/usecases/_meta_library_template_fetch.py`:

1. A pure adapter
   `adapt_meta_library_template_response(raw: Optional[Dict[str, Any]]) -> Optional[TemplateInfo]`
   that takes a Meta library-catalog response item and runs it
   through `TemplateTranslationAdapter` + Decision 12's
   component-validation guard, returning the local `TemplateInfo`
   shape (or `None` when the input is `None`). Pure transformation,
   no HTTP call.
2. A Direct-Send-specific fetch wrapper
   `fetch_meta_library_template_metadata(meta_service, template_name, language) -> Optional[TemplateInfo]`
   that calls
   `meta_service.fetch_library_template_by_name_and_language(name, language)`
   (the new exact-match method introduced in Decision 4) and
   delegates to (1). Only the Direct Send branch uses this wrapper.

`ValidatePreApprovedTemplatesUseCase._get_template_info` keeps
calling `meta_service.get_pre_approved_template(name, language)`
(fuzzy semantics preserved per Decision 4) and is collapsed into a
3-line call that delegates the response to (1) — the adapter. The
legacy push-time validation's external behavior is therefore
unchanged (same HTTP call, same first-hit selection); only the
adapter step is deduplicated.

**Rationale**:

- Both paths (push-time validation, Direct-Send assignment) need
  the same Meta-library-catalog → local-`Template.metadata`
  transformation. Duplicating it creates the worst kind of drift
  (a future Meta response field added to one but not the other).
- Splitting the transformation (pure adapter) from the HTTP call
  (Direct Send-only wrapper) preserves Decision 4's guarantee that
  the push-time validation keeps its fuzzy-search semantics — the
  legacy `get_pre_approved_template` continues to be the push-time
  HTTP call, and only the response shaping is shared.
- Extracting into a free function rather than a use case mirrors
  the project's existing private-helper patterns (`_base_library_template.py`,
  `_base_template_creator.py`). It's not a domain operation; it's
  a content-shape adapter.
- The `TemplateTranslationAdapter` is already designed for this job
  and is already covered by tests; we do not reinvent it.

**Alternatives considered**:

- *Keep the body inlined in `validate_templates.py` and copy-paste
  for Direct Send*: rejected (drift risk).
- *Rename `ValidatePreApprovedTemplatesUseCase._get_template_info`
  to a public method and call it from the assignment use case*:
  rejected because it would couple the assignment use case to a
  push-time use case; the helper is an architecturally cleaner
  shared dependency.
- *Have the helper call `fetch_library_template_by_name_and_language`
  for both paths (so push-time validation transparently becomes
  stricter)*: rejected because Decision 4 explicitly preserves the
  fuzzy semantics of `get_pre_approved_template` for the existing
  push-time caller; switching that call to exact-match + language
  guard would be a silent behavior change for the legacy validation
  flow and would invalidate existing `_get_template_info` tests.

**Post-design fold-in (Session 2026-05-22 — FR-003e / FR-003f /
auxiliary-field drop)**: the spec was clarified after this Decision
was first written. The pure adapter
`adapt_meta_library_template_response` is the single touch point for
the three new rules — `data-model.md §5` ("Adapter normative
behaviour") now pins them as the adapter's normative contract, and
`tasks.md` Phase 8 (T107–T111) covers them with TDD-first tests
against `test_meta_library_template_fetch.py`. The split between
adapter and HTTP wrapper (above) is what makes the fold-in surgical:
the Direct Send wrapper does not change, only the shared adapter
tightens its validation. The push-path caller
(`ValidatePreApprovedTemplatesUseCase`) inherits the tighter
validation transparently — that's intentional, because Meta's
library catalog is the same upstream surface for both callers and a
malformed-response shape is malformed regardless of which path is
fetching it. Pre-existing `test_validate_pre_approved_templates.py`
tests continue to pass because the OrderStatus templates the legacy
path validates already comply with FR-003e / FR-003f / the drop-rule;
if a future PR ever extends the legacy path to a template family
that does NOT comply, the adapter-shared validation will surface the
incompatibility uniformly across both paths — by design.

---

## Decision 10 — Where the broadcast-disabling check for `PAUSED`/`FLAGGED` lives

**Decision**: Tighten the *single* current dispatch gate at
`Broadcast.get_current_template`
(`retail/agents/domains/agent_webhook/services/broadcast.py:602`). The
existing `current_version__status="APPROVED"` filter (inside that
method) already excludes every non-APPROVED status — but we add an
explicit sibling lookup that:

1. When the lookup-without-status filter finds a template whose
   `current_version.status` is in `{PAUSED, FLAGGED}`, emits an
   audit log entry with the template name, the version status,
   and the originating order-status event before returning `None`.
2. When the lookup-without-status filter finds a template whose
   `current_version.status` is in any other non-APPROVED state
   (legacy: `PENDING`, `REJECTED`, …), keeps the existing log line
   shape (no behavior change).

The same tightening is applied to
`SendTestTemplateUseCase._get_active_template`
(`retail/api/integrated_agent/usecases/send_test_template.py:50`).

**Rationale**:

- The dispatch gate is a single point. The implementation already
  rejects `PAUSED`/`FLAGGED` automatically (they aren't `APPROVED`),
  so there is no logic change. What's missing is the **audit log
  entry** that Story 3 mandates.
- The audit log is the only observable difference between
  "pre-existing skip behavior" (FR-008, FR-012, FR-015 last clause)
  and "new PAUSED/FLAGGED skip behavior". Surfacing it from the
  central gate avoids scattering the audit logic.

**Alternatives considered**:

- *Add a status filter `status__in=["APPROVED"]` and rely on a
  separate query for the audit log*: rejected — two queries per
  miss, no functional gain.
- *Move the gate into a dedicated `DispatchEligibilityChecker`
  class*: tempting, but the gate is two lines of code; class-ifying
  it would be a constitution violation (premature abstraction).

---

## Decision 11 — How the Direct Send broadcast is built

**Decision**: Extend the existing `Broadcast` class in
`retail/agents/domains/agent_webhook/services/broadcast.py` with a
new method `build_direct_send_message(...)` that mirrors the
signature of `build_broadcast_template_message` and produces the
Direct Send payload shape (Decision 8). The dispatch entry point
`build_message(...)` chooses between the two:

```python
def build_message(self, integrated_agent, data):
    template = self.get_current_template(integrated_agent, data)
    if template is None:
        return None
    if integrated_agent.config.get("direct_send", False):  # data-model.md §1
        return self.build_direct_send_message(...)
    return self.build_broadcast_template_message(...)
```

**Rationale**:

- The existing `Broadcast` class already owns dispatch payload
  construction; adding a sibling method preserves the discovery
  story for any new reader ("everything dispatch-related lives in
  this class").
- Two separate methods make the Direct-Send shape independently
  testable without exercising the legacy logic, and vice versa
  — Story 4's "no regression on the legacy path" is much easier
  to enforce when the two methods are textually disjoint.
- A simple `if integrated_agent.config.get("direct_send", False)`
  at the routing point makes the path selection explicit; this is
  what the spec asks for ("the dispatch path is chosen by the
  IntegratedAgent's flag"). The `config.get(...)` form is mandated
  by `data-model.md §1` — direct attribute reads (`obj.direct_send`)
  are forbidden because the field does not exist on the model.

**Alternatives considered**:

- *Strategy pattern (`DirectSendBuilder` / `LegacyBuilder`
  classes injected via DI)*: tempting but for two builders with
  no other dimensions to vary it adds two interfaces, two
  classes, and a factory — complexity tracking would have to
  justify it. Two methods on the existing class are clearer
  for a v1.
- *Branch deep inside `build_broadcast_template_message`*: would
  pollute the legacy method with `if direct_send` checks and
  reintroduce the regression risk Story 4 protects against.

---

## Decision 12 — Unsupported components for OrderStatus templates

**Decision**: At assignment time, after fetching from Meta's library
catalog, **validate** each template against the supported component
set (body required, optional text/image header, optional footer,
optional single CTA URL or up to three reply buttons). If a fetched
template uses an unsupported component (carousel, list, catalog,
order_details, flow message), the assignment fails atomically with
`DirectSendUnsupportedComponentError`.

**Rationale**:

- The spec lists this as out of scope for v1 (Edge Case in spec).
- Meta's library-catalog response could conceivably evolve to
  include components Direct Send doesn't support; failing fast at
  assignment-time is much cheaper than discovering it at the first
  broadcast.
- The OrderStatus templates today only use body + optional image
  header + optional URL button, so this validation will never
  trigger in production at v1; it exists as a defense-in-depth.

**Alternatives considered**:

- *Skip validation and let dispatch silently drop*: rejected
  because dispatch-time failures are observable only as missing
  messages on the customer side.
- *Filter unsupported components and persist a stripped Template*:
  rejected because the resulting message would not match what the
  customer's content team approved with Meta.

---

## Decision 13 — Default for `IntegratedAgent.direct_send` on existing rows

> **⚠️ SUPERSEDED by `data-model.md §1` (spec correction).** No
> column is added to `IntegratedAgent`, so the question of its
> "default value at backfill time" is moot. The flag lives inside the
> existing `IntegratedAgent.config` JSONField; legacy rows have no
> `direct_send` key and `obj.config.get("direct_send", False)`
> collapses absence to `False` — which is exactly the legacy behaviour
> (FR-005). No `IntegratedAgent` migration ships with this feature.
> The text below is preserved for historical auditability only.

**Original decision (HISTORICAL)**: The migration that adds the `direct_send` column
populates every existing row with `False`. The default on the model
is `False`. No data backfill from the channel is performed.

**Original rationale (HISTORICAL)**:

- Story 4 requires the legacy path to behave identically to today,
  so existing IntegratedAgents must default to "not Direct Send".
- The flag is documented as a *snapshot at assignment time*
  (Assumption in spec, FR-002). Backfilling from the channel would
  break that contract for projects whose channel was flipped after
  the IntegratedAgent was created.
- A simple `default=False` migration is the cleanest possible
  rollout.

**Alternatives considered (HISTORICAL)**:

- *Backfill from each project's channel via a data migration*:
  rejected for the snapshot-correctness reason above.
- *Enable Direct Send opportunistically on the first dispatch*:
  rejected because it shifts the source of truth into the runtime
  path and undoes the spec's "snapshot at assignment time" guarantee.

---

## Decision 14 — Test isolation for the Meta and Integrations clients

**Decision**: All new tests follow Constitution Principle III:

- `MetaService` and `IntegrationsService` are injected into use cases
  via the existing `Optional[Interface] = None` pattern; in tests we
  pass `MagicMock(spec=...)` instances.
- HTTP layers (`MetaClient`, `IntegrationsClient`) are exercised by
  `unittest.mock.patch` on `requests` / `make_request`.
- Cache, queue, OIDC, S3 are not touched by the new tests.
- For tests that need a Django cache (e.g. order-status duplicate
  detection if exercised), they `@override_settings(CACHES={"default":
  LocMemCache})`.
- Coverage parity is verified locally before opening the PR with
  `poetry run coverage run manage.py test` followed by
  `poetry run python contrib/compare_coverage.py`.

**Rationale**: this is the constitution; not a real "decision" — it's
documented here so the implementer doesn't have to re-derive it.

---

## Decision 15 — Idempotency & retry-safety model

**Decision**: the feature inherits — and explicitly restates — the
project's pre-existing idempotency model:

1. **"Single logical broadcast"** = the tuple
   `(Project, IntegratedAgent.uuid, OrderStatusDTO.orderId,
   OrderStatusDTO.currentState)` (spec FR-028 / Exactly-Once Dispatch
   invariant). The `Project` component is identified by either its
   FK integer (`Project.id` / `IntegratedAgent.project_id`) or its
   UUID — both uniquely identify the same row; serialization is an
   implementation detail per FR-028's serialization rule. The
   current implementation uses the FK integer in the cache-key
   string for compactness.
2. **Trigger-side dedup** at the order-status webhook entry point via
   atomic `cache.add` keyed on the tuple above
   (`_is_duplicate_event`,
   `retail/agents/domains/agent_webhook/usecases/order_status.py:181-211`),
   with a configurable window
   (`ORDER_STATUS_DUPLICATE_WINDOW_SECONDS`, default 60s).
3. **Persistence-side dedup** via the conditional unique constraints
   already shipped on `BroadcastMessage` (`broadcast_id`,
   `external_message_id`) and on `BroadcastConversion`
   (`(project, order_id)`).
4. **Retry budget = 0 on the hot path**: Retail does not originate
   retries inside the dispatch use case. The system IS retry-safe
   (tolerant of broker redeliveries, Flows replays, operator
   re-assignment) but never originates one. The single Retail-side
   retry surface is operator-initiated assignment retry after
   FR-003d, which is a fresh `AssignAgentUseCase.execute` invocation
   (a new atomic block, not a Celery-level retry). Celery's
   `task.retry(...)` mechanism is NOT used by this pipeline (spec
   FR-038); re-delivery comes from the broker (RabbitMQ) for
   `BroadcastConsumer` (absorbed by FR-035) or from the upstream
   caller re-firing the entry-point task (absorbed by FR-028's
   dedup + FR-036's `get_or_create`).
5. **Cache failure mode = fail-CLOSED**: if Redis is unreachable
   mid-trigger, `cache.add` raises and the order-status entry point
   propagates — the trigger fails fast, no `BroadcastMessage` is
   persisted, no Flows POST is issued. The conservative default
   prevents silent duplicate dispatches on infra outages.
6. **Audit-log shape catalogue** (FR-039) pins six disjoint shapes —
   five refusal classes (dedup skip, PAUSED/FLAGGED skip, Direct
   Send validation skip, legacy non-APPROVED skip, Direct Send
   assignment atomic failure) and one admission class (order-status
   agent resolution). Log consumers route per class without parser
   churn; the admission shape is what makes FR-031's official-vs-
   parent-flagged decision observable from logs without re-deriving
   it from row state.

**Rationale**:

- The existing dedup mechanism (`cache.add` + the canonical tuple)
  is already in production for the legacy path; restating it as a
  requirement makes the legacy/Direct-Send cohort treatment
  symmetric and forbids a divergence under future refactors.
- Tuple components are normative because they encode the spec's
  Edge Case taxonomy: `current_state` separates `invoiced` from
  `shipped` (so they don't collapse — FR-030); `integrated_agent.uuid`
  separates an official OrderStatus agent from a parent-flagged
  custom agent without forcing a per-agent lookup at admission time.
- Persistence-side dedup picks up where trigger-side dedup leaves
  off — e.g. if the dedup window expires and a stale webhook
  re-arrives, the `BroadcastMessage` row's unique constraints
  catch it on the Flows-side replay because the same `broadcast_id`
  hashes to the same row.
- Retry budget = 0 is the team's existing operational stance for
  this hot path; documenting it removes ambiguity at design review
  ("should we add a Celery retry on `Broadcast.send_message`?" →
  no, the spec forbids it).
- Fail-closed on cache outage is the safer default for an outbound
  customer-messaging system: a missed dispatch is a recoverable
  observability issue, a duplicate dispatch is a user-facing one.

**Conflict resolution — operator retry vs.
`Contract:meta-library-catalog §4` (idempotency.md CHK047)**:

`Contract:meta-library-catalog.md §4` documents "no retry policy
in v1; library catalog is read at most once per template per
assignment". Spec Edge Cases say "the operator can retry once Meta
has the content (or recovers)". These are consistent because the
unit "per assignment" is per-assignment-ATTEMPT — every operator
retry starts a NEW `AssignAgentUseCase.execute` invocation with
its own `@transaction.atomic` and its own fresh per-template
catalog fetches. No state from the failed prior attempt is
re-used (Decision 5 + this Decision 15, fail-atomic semantics).
The contract has been amended to make this explicit.

**Correlation identifier**: no new `trace_id` is introduced. The
existing identifiers — `OrderStatusDTO.orderId`,
`IntegratedAgent.uuid`, `BroadcastMessage.uuid`, `broadcast_id`,
`external_message_id` — already stitch a single logical dispatch
across logs, EDA events, and retry attempts. FR-039 standardizes
the log shapes so operators can grep on `agent_uuid={...}` +
`order_id={...}` and reconstruct the timeline; this is the cheapest
correlation mechanism and avoids touching every log site in the
codebase.

**Alternatives considered**:

- *Issue an explicit `event_id` UUID at the order-status webhook
  entry and propagate it through Lambda / Flows / EDA*: rejected
  for v1 — it would require coordinated changes in Lambda, Flows,
  and the broker consumer, all of which are owned by sibling teams.
  Documented as a future cross-cutting observability item.
- *Move dedup to a per-`BroadcastMessage` write-time check (drop
  the `cache.add` trigger-side gate)*: rejected because it shifts
  duplicate detection AFTER the Flows POST has fired, which
  defeats the entire purpose of "no duplicate POST".
- *Add a Celery retry on `Broadcast.send_message`*: rejected
  because Flows is the retry layer for outbound delivery; doubling
  the retry budget would compound duplicates.
- *Fail-OPEN on cache outage (allow possible duplicate to avoid
  losing a dispatch)*: rejected as the v1 default — duplicates
  are user-facing and irrecoverable, while a missed dispatch is
  observable and recoverable via the next VTEX webhook.

---

## Decision 16 — Tenant Isolation Model

**Decision**: the feature inherits — and explicitly restates — the
project's tenant-isolation model:

1. **Canonical tenant identifier** is `Project.uuid` (Retail-internal
   UUID). Every read or write against `IntegratedAgent`, `Credential`,
   `Template`, `Version`, `BroadcastMessage`, `BroadcastConversion`
   MUST be scoped through the FK chain that ends at `Project` (spec
   FR-040). `Project.id` (FK integer) and `Project.uuid` are
   serialization-equivalent for tenant-scoping purposes — both
   identify the same row uniquely. `Project.vtex_account` is the
   external tenant identifier, with the documented "duplicate →
   return None" SECURITY BOUNDARY at the order-status entry point
   (`get_project_by_vtex_account`).
2. **Tenant FK chain**: `BroadcastMessage`, `BroadcastConversion`,
   `IntegratedAgent` carry direct FKs to `Project`. `Credential`,
   `Template` chain through `integrated_agent.project`. `Version`
   has BOTH a transitive chain through `template.integrated_agent`
   AND a direct FK on `Version.project` (dual-path scoping). The
   redundant direct FK exists so the dispatch-time queryset at
   `Broadcast.get_current_template` can filter by project without
   joining through `Template`. The invariant
   `Template.integrated_agent.project_id == Version.project_id` MUST
   hold for every (Template, Version) pair.
3. **Multi-credential surface taxonomy**: four distinct credential
   surfaces, three different tenant scopes —
   - `META_SYSTEM_USER_ACCESS_TOKEN` (CROSS-tenant, library-catalog
     reads only at agent-assignment time);
   - Channel-side WhatsApp Cloud credentials (PER-tenant, consumed
     at dispatch time via Flows);
   - Flows internal-auth token (CROSS-tenant by design, every
     project's broadcast POST uses the same token; tenant scoping
     enforced by Flows on its side via the request body's `project`
     field);
   - Per-agent `Credential` rows (PER-tenant, FK-chained to
     `integrated_agent.project`).
4. **Inbound EDA tenant resolution**: the supported mechanisms are
   (a) `Project.uuid` carried in the event payload; (b)
   `BroadcastMessage.broadcast_id` lookup (safe because Flows
   guarantees `broadcast_id` global uniqueness); (c)
   `BroadcastMessage.external_message_id` lookup (safe because Meta
   guarantees `external_message_id` global uniqueness on its side);
   (d) `Project.vtex_account` lookup with the fail-closed
   `MultipleObjectsReturned → return None` boundary. Any other
   mechanism MUST justify global uniqueness across tenants
   (FR-041).
5. **Outbound EDA / datalake events** carry
   `project=str(integrated_agent.project.uuid)` as a required field
   so downstream analytics never aggregates across tenants
   (FR-042). The pinned audit point is
   `Broadcast._send_to_datalake`'s `event_data["project"]` write.
6. **Cache key project-scoping**: every cache key materializing
   tenant-scoped state includes a project component
   (`order_status_event:{project_id}:{integrated_agent.uuid}:{order_id}:{current_state}`,
   `project_by_vtex_account_{vtex_account}`,
   `project_by_uuid_{project.uuid}`,
   `project_domain_{project.uuid}`). Documented in `plan.md`
   Constraints — Tenant isolation. Future cache-key changes that
   drop the project component or replace it with a non-globally-unique
   component are forbidden regressions.
7. **Per-IntegratedAgent uniqueness scope** for `Template.name`
   AND `Version.template_name`: today neither column carries a
   `unique=True` constraint (removed in
   `templates/0007_alter_template_name.py` and
   `templates/0015_alter_version_template_name.py`); the
   uniqueness scope is per-IntegratedAgent (FR-045). A future
   migration that re-introduces a global `unique=True` constraint
   on either column is a forbidden regression because Direct Send's
   per-WABA uniqueness rule (each project has its own WABA) maps to
   per-IntegratedAgent uniqueness on Retail's side.
8. **Lambda function-name namespace** (per-project): the per-agent
   Lambda is invoked by name `retail-setup-{hash_13_digits}` where
   the hash is `SHA256(agent.name + agent.uuid.hex)`
   (`retail/agents/domains/agent_management/usecases/push.py:112-123`).
   `Agent.project` is a per-project FK so the function-name
   namespace is per-project by construction; the IAM role attached
   to Retail is scoped so that only function names following this
   convention can be invoked. This is the upstream precondition
   that closes the "rule engine for project A invokes project B's
   Lambda" surface.
9. **Per-tenant DB scoping at the assignment surface**: the
   spec's required cross-validation between the `app_uuid` query
   parameter and the `Project-Uuid` header (FR-043) is satisfied at
   v1 transitively — DRF's `HasProjectPermission` gates the operator
   to `Project-Uuid`, Integrations Engine's authorization on the
   channel-app endpoint gates `app_uuid` reads to the channel's
   owner project, and `IntegrationsService.get_channel_app(...)`
   returns `None` on any HTTP error (fail-closed). The explicit
   Retail-side cross-validation
   (`app.config.project_uuid == request.headers["Project-Uuid"]`
   with HTTP 403 on mismatch) is captured as a defense-in-depth
   follow-up scoped to a separate PR (see `plan.md` Constraints —
   Tenant isolation).

**Rationale**:

- The FK chain + the canonical-identifier rule make tenant scoping
  evaluable at code review by a single check: "does this query end
  at `Project` (directly or via FK)?" — a simpler invariant than
  "does this query carry the right `project_uuid` argument?".
- The dual-path scoping on `Template` / `Version` documents an
  intentional schema redundancy that already lives in the codebase
  (the direct `Version.project` FK was added in
  `templates/0001_initial.py`); without restating it, a future
  refactor could drop the direct FK to "simplify" the schema and
  silently make cross-tenant queries cheaper.
- The credential surface taxonomy resolves the user-query
  ambiguity: "Meta credentials" without a surface label is
  ambiguous, and the spec MUST disambiguate to make tenant
  reasoning evaluable. The cross-tenant surfaces (`META_SYSTEM_USER_ACCESS_TOKEN`,
  Flows internal-auth token) are explicitly justified by the
  resource being either Meta-curated public content or Weni-internal
  service traffic — i.e. the resource itself is cross-tenant, so a
  cross-tenant credential is acceptable.
- Documenting the FK chain + the deterministic tenant-resolution
  mechanisms also makes SC-010's measurability claim defensible:
  the SQL invariants in SC-010 (a)–(d) are direct consequences of
  the FK chain plus the assignment-time write logic, and the audit
  query in `tasks.md` T035c materializes invariant (a) as a
  CI-runnable assertion (a two-project cross-tenant regression
  guard that also asserts the dedup cache key, datalake event
  payload, and per-IntegratedAgent template lookup remain
  tenant-scoped).

**Conflict resolution — single global Meta system token vs.
per-tenant retry independence (CHK048)**:

The `META_SYSTEM_USER_ACCESS_TOKEN` is a CROSS-TENANT credential by
design (item 3 above). A Meta-side rate-limit applied to that token
reduces every project's library-catalog GET success rate at the
same time, and operator retries (per FR-003d) cannot independently
isolate one tenant from another at the credential level. The
spec's "operator can retry once Meta has the content (or recovers)"
text (Edge Cases) is therefore a per-PROJECT statement about local
retry semantics, not a guarantee that one tenant's retry storm
cannot consume another tenant's effective rate-limit budget.

This is an accepted trade-off for v1:

- The alternative (per-tenant Meta access tokens) requires
  Beta-program-level cooperation from Meta to issue per-WABA
  system-user tokens, plus a credential-management layer in
  Retail to store and rotate them. Both are well outside the
  scope of this feature.
- The blast radius is bounded because library-catalog reads are
  agent-assignment-time-only — there is no dispatch-time
  dependency on this token. A Meta rate-limit blocks NEW
  assignments but not existing tenants' broadcasts.
- The conservative `MultipleObjectsReturned → None` boundary at
  the order-status entry point (item 1, security boundary) is
  scoped to project resolution from `vtex_account`, NOT to Meta
  rate-limits, so the two boundaries are independent.

Documented as an Edge Case in spec.md (Single Meta system token
rate-limit) and as a known cross-tenant blast-radius point in
`contracts/meta-library-catalog.md` §9.

**Alternatives considered**:

- *Issue per-tenant Meta system-user tokens at agent-assignment
  time*: rejected for v1 (requires Meta Beta cooperation and a
  credential-management layer in Retail; both are larger scope
  than this feature).
- *Add a Django middleware / queryset wrapper that enforces tenant
  scoping at every read*: tempting but rejected for v1 — the FK
  chain + code review + the SC-010 audit query are the merge gate.
  A queryset wrapper would force every unrelated PR to either pass
  through the wrapper or carry an explicit "tenant-less" annotation,
  which is high-friction for read paths that don't touch
  tenant-scoped models. Documented as a future enhancement in
  `plan.md` Constraints — Tenant isolation.
- *Persist a `tenant_id` column on every tenant-scoped model and
  enforce it via a Django signal*: rejected — `tenant_id` would
  duplicate `project_id`, and the FK chain already provides the
  same guarantee at zero extra cost.
- *Stop using the `MultipleObjectsReturned → None` boundary and
  raise instead*: rejected — raising surfaces the same outcome
  (no dispatch fired) but at a higher operator-noise cost; the
  current "log + return None" boundary is observable through the
  `[ORDER_STATUS] multiple_projects` log line and is the v1
  default. Switching to raise would be a separate spec change.

---

## Resolved `NEEDS CLARIFICATION` items

The spec's Clarifications block resolved three items at clarify time
on 2026-05-20 (language source, project-locale resolution, fallback
semantics) and three more on 2026-05-22 (header plain-string shape
+ normalization → FR-003e; button-type strict rejection + dual URL
shape normalization → FR-003f; auxiliary curation field drop at
fetch time → Q3 drop-rule). The 2026-05-22 trio post-dates this
research document and is folded into the adapter contract via
Decision 9's "Post-design fold-in" sub-section (above),
`data-model.md §5` ("Adapter normative behaviour"), `plan.md`
Constraints sub-section "Post-design spec updates folded in", and
`tasks.md` Phase 8 (T107–T111). No new research Decision is
required because the three rules collapse onto Decision 9's
single-adapter touch point and reuse Decision 12's existing
`DirectSendUnsupportedComponentError`. This research document
resolves the remaining plan-time decisions listed below; **after
this document, no `NEEDS CLARIFICATION` remains in the plan**:

- ✅ Decision 1 — `direct_send` storage location (**superseded by `data-model.md §1`**: stored as a key inside `IntegratedAgent.config` JSON, not as a new column).
- ✅ Decision 2 — OrderStatus agent identification.
- ✅ Decision 3 — Channel Direct Send flag lookup.
- ✅ Decision 4 — Meta library-catalog fetch helper.
- ✅ Decision 5 — `pt_BR` fallback algorithm.
- ✅ Decision 6 — Variable substitution algorithm (incl. missing /
  extra indices).
- ✅ Decision 7 — Direct Send identifier rule violation handling.
- ✅ Decision 8 — Messaging gateway payload shape.
- ✅ Decision 9 — Library-catalog → local Template adapter sharing.
- ✅ Decision 10 — Broadcast-disabling check for `PAUSED`/`FLAGGED`.
- ✅ Decision 11 — Direct Send broadcast builder placement.
- ✅ Decision 12 — Unsupported-component handling.
- ✅ Decision 13 — Default flag for existing IntegratedAgents (**superseded by `data-model.md §1`**: no column ships, so legacy rows have no key and `config.get("direct_send", False)` is the canonical read).
- ✅ Decision 14 — Test isolation strategy.
- ✅ Decision 15 — Idempotency & retry-safety model (canonical
  tuple, retry budget, cache failure mode, retry-as-new-assignment
  conflict resolution, correlation identifier).
- ✅ Decision 16 — Tenant isolation model (canonical tenant
  identifier, FK chain, multi-credential surface taxonomy, EDA
  consumer tenant resolution, cache project-scoping, Lambda
  function-name namespace, FR-043 v1 implementation status,
  conflict resolution between cross-tenant Meta system token and
  per-tenant retry independence).
