# Phase 0 Research: Template Sample Validation Endpoint for Direct Send

**Feature**: `004-template-sample-validation`
**Date**: 2026-05-26
**Spec**: `./spec.md`

This document records the design decisions taken to remove every
`NEEDS CLARIFICATION` from the plan and the alternatives rejected
on the way. Each decision is sized so a single PR can implement it
without reopening this file. Decisions are organized in the order
an implementer encounters them while reading `plan.md` top-to-bottom.

The spec carried zero `NEEDS CLARIFICATION` markers at planning
time (the user's iterative refinement during `/speckit-specify`
collapsed the open decisions into concrete assumptions A1–A12).
The decisions below restate those resolutions in the form an
implementer needs.

---

## Decision 1 — Endpoint placement and composition

**Decision**: The new endpoint sits on the existing `TemplateViewSet`
(`retail/templates/views.py`) as a DRF detail action:

```python
@action(detail=True, methods=["post"])
def sample(self, request: Request, pk: UUID) -> Response:
    ...
```

The URL path is `POST /api/v3/templates/<template_uuid>/sample/`,
generated automatically by the existing DRF `DefaultRouter` in
`retail/templates/urls.py:11-13` from the `@action(detail=True)`
declaration.

**Rationale**:

- The spec's FR-001 mandates the new endpoint be under the
  existing `retail.templates.urls` namespace and pin the URL
  shape to `POST /api/v3/templates/<template_uuid>/sample/`.
- Co-location with the existing PATCH endpoint on the same
  `TemplateViewSet` matches the existing layout convention. The
  ViewSet already has detail actions (e.g. `status` at
  `views.py:71-81` and `custom` at `views.py:127-139`) so adding
  another detail action follows the established pattern.
- DRF's `DefaultRouter` auto-generates the URL from the
  `@action(detail=True, methods=["post"])` declaration; no manual
  entry in `urls.py` is needed for the new path (the
  router-generated path is `/<basename>/<pk>/<action_name>/` →
  `/templates/<uuid>/sample/`).
- The endpoint inherits
  `permission_classes = [IsAuthenticated, HasProjectPermission]`
  from the ViewSet class (FR-002).

**Alternatives considered**:

- *Place the new endpoint under a new top-level
  `retail.templates.sample_views` module*: rejected because the
  spec's FR-001 explicitly says "the new endpoint MUST sit on the
  same `TemplateViewSet`". A new module would also force the
  serializer + URL wiring to diverge from the existing PATCH
  endpoint, defeating FR-014's request-shape parity guarantee.
- *Reuse the existing `partial_update` view method with a query-string
  toggle (e.g. `?validate_sample=true`)*: rejected because the two
  flows have different response shapes (the PATCH endpoint returns
  `ReadTemplateSerializer.data` directly; the new endpoint returns
  a wrapper `{category, template_updated, template,
  meta_sample_response}`) and different idempotency contracts.
  Bundling them would force a Liskov-violating internal branch and
  break the single-responsibility guarantee of each method.

---

## Decision 2 — Direct Send-eligibility gating happens at the use-case layer

**Decision**: The eligibility check
`template.integrated_agent and template.integrated_agent.config.get("direct_send", False)`
runs INSIDE the use case, immediately after the Template is loaded
(with `select_related("integrated_agent")`) and BEFORE any Meta
call. On a failed check the use case raises a domain exception
`NotDirectSendEligibleError` which the view translates into
HTTP 400 with body
`{"detail": "Template is not Direct Send-eligible", "error_code": "not_direct_send_eligible"}`
(FR-002a / FR-007e).

**Rationale**:

- A DRF permission class cannot perform this check — permission
  classes run BEFORE `pk` resolution and BEFORE any DB lookup, so
  they don't have the Template row in hand.
  `permission_classes` is the wrong tool for a check that depends
  on resource state.
- The gate is a domain rule ("is this template configured for the
  Direct Send dispatch path"), not an authorization rule ("is this
  user allowed to access this resource"). Constitution Principle I
  pins domain rules to the Use Case layer.
- The check costs zero extra queries: `template.integrated_agent`
  is already loaded via the `select_related("integrated_agent")`
  on the Template lookup that the use case needs regardless (the
  shared helper `_apply_metadata_update` per Decision 4 invokes
  `get_agent_config(template.integrated_agent)`, so the relationship
  is hot).
- The predicate is the SAME flag set at assignment time
  (`retail/agents/domains/agent_integration/usecases/assign.py:162`)
  and read at dispatch time
  (`retail/agents/domains/agent_webhook/services/broadcast.py:932`).
  No parallel eligibility definition is introduced.

**Alternatives considered**:

- *Add a custom permission class
  `IsDirectSendEligibleTemplate` that loads the Template inside
  `has_object_permission`*: rejected because (a) DRF's
  `has_object_permission` requires `get_object()` to be called by
  the view, which forces the view to load the Template — pushing
  ORM access into the view layer (Constitution Principle I
  violation); and (b) loading the same Template twice (once in
  the permission class, once in the use case) is wasteful.
- *Filter the gate at the queryset level (
  `Template.objects.filter(integrated_agent__config__direct_send=True).get(uuid=...)`),
  so non-eligible templates return HTTP 404 instead of HTTP 400*:
  rejected because HTTP 404 ("not found") is the wrong semantic
  — the template DOES exist; it's just not eligible for this
  operation. HTTP 400 with a descriptive `error_code` lets the
  frontend differentiate "use the PATCH endpoint instead" from
  "this template doesn't exist".
- *Skip the gate entirely and let the request proceed*: rejected
  because (a) it would burn Meta sample-API quota on templates
  whose dispatch path is the legacy Flows broadcast (where the
  sample verdict doesn't gate dispatch), and (b) FR-006d's
  "skip PENDING, write APPROVED directly" rule only holds for
  Direct Send templates — applying it to non-eligible templates
  would mark them APPROVED without the legacy Flows path actually
  having approval, breaking the legacy dispatch (spec.md A8).

---

## Decision 3 — WABA-id resolution path

**Decision**: The WABA id is resolved per-call from
`ProjectOnboarding.config["channels"]["wpp-cloud"]["channel_data"]["waba_id"]`.
The use case fetches the `ProjectOnboarding` row by
`project__uuid=dto.project_uuid`. When the row is missing, the
`channels.wpp-cloud` key is missing, the `channel_data.waba_id`
field is missing, or the value is empty, the use case raises
`WabaNotConfiguredError` which the view translates into HTTP 400
with body
`{"detail": "WABA not configured for this project", "error_code": "waba_not_configured"}`
(FR-005a / FR-007d).

**Rationale**:

- This is the same lookup path
  `retail/projects/usecases/configure_wpp_cloud.py:96-114` uses to
  feed `create_wpp_cloud_channel` and the same path
  `retail/projects/usecases/configure_one_click_payment.py:182-219`
  uses to feed `MetaService.create_flow`. Reusing it keeps WABA-id
  resolution in one place (spec.md A2).
- There is no `Project.waba_id` shortcut and no
  `IntegratedAgent.waba_id` column today — `IntegratedAgent.channel_uuid`
  is a different identifier (the WhatsApp channel UUID, NOT the
  WABA id). Denormalizing the WABA id onto `Project.config` is
  out of scope for v1 (spec.md A2).
- The lookup is O(1) (`ProjectOnboarding.project_id` is a unique
  FK to `Project`) and adds at most one DB round-trip to the hot
  path. The latency budget (SC-006 — p99 < 3s) absorbs it
  comfortably (the outbound Meta call dominates).

**Alternatives considered**:

- *Denormalize `waba_id` onto `Project.config["waba_id"]` at
  channel-setup time*: rejected for v1 because it forces a
  follow-up migration / consumer update on the
  `ProjectUpdateConsumer` path and a backfill for existing
  projects. If operational data later shows the per-call lookup
  is the latency bottleneck (it won't — Meta's call dominates),
  a denormalization is a small follow-up PR.
- *Resolve `waba_id` from the IntegratedAgent's `channel_uuid`
  via an outbound Integrations-engine call*: rejected because (a)
  it adds an outbound HTTP round-trip on the hot path, (b) it
  doubles the per-request quota cost (sample API + Integrations
  API), and (c) `channel_uuid` ↔ `waba_id` resolution is
  Integrations' internal concern that Retail shouldn't need to
  re-derive when the value is already snapshot'd on
  `ProjectOnboarding`.

---

## Decision 4 — Strategy refactor: extract `_apply_metadata_update` and `_create_version_with_options`

**Decision**: Extract two private helpers from
`UpdateNormalTemplateStrategy.update_template`
(`retail/templates/strategies/update_template_strategies.py:223-236`)
and the parent class:

```python
def _apply_metadata_update(
    self, template: Template, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Build canonical metadata, write Template.metadata, sync
    abandoned-cart config, return translation_payload for downstream
    callers. Encapsulates _update_common_metadata +
    template.save(update_fields=["metadata"]) +
    _sync_abandoned_cart_image_config."""
    updated_metadata, translation_payload = self._update_common_metadata(
        template, payload
    )
    template.metadata = updated_metadata
    template.save(update_fields=["metadata"])
    self._sync_abandoned_cart_image_config(template, translation_payload)
    return translation_payload

def _create_version_with_options(
    self,
    template: Template,
    payload: Dict[str, Any],
    *,
    status: str,
    advance_current_version: bool,
) -> Version:
    """Create a new Version row with the given status, optionally
    advancing Template.current_version to it. Encapsulates the
    existing _create_version + the optional current_version
    repointing."""
    version = self._create_version(
        template=template,
        app_uuid=payload["app_uuid"],
        project_uuid=payload["project_uuid"],
    )
    if status != "PENDING":
        version.status = status
        version.save(update_fields=["status"])
    if advance_current_version:
        template.current_version = version
        template.save(update_fields=["current_version"])
    return version
```

The existing `update_template` recomposes them as:

```python
def update_template(self, template, payload):
    translation_payload = self._apply_metadata_update(template, payload)
    version = self._create_version_with_options(
        template, payload,
        status="PENDING",
        advance_current_version=False,
    )
    self._notify_integrations(
        version_name=version.template_name,
        version_uuid=version.uuid,
        translation_payload=translation_payload,
        app_uuid=payload["app_uuid"],
        project_uuid=payload["project_uuid"],
        category=template.metadata.get("category"),
    )
    return template
```

The new `ValidateTemplateSampleUseCase` (on the UTILITY path)
composes:

```python
translation_payload = strategy._apply_metadata_update(template, payload)
strategy._create_version_with_options(
    template, payload,
    status="APPROVED",
    advance_current_version=True,
)
# STOP — no _notify_integrations call (A10 / FR-006 / FR-006d)
```

**Rationale**:

- FR-006a's recommendation: "EXTRACT the existing
  `UpdateNormalTemplateStrategy.update_template` body into smaller
  building-block helpers". This refactor implements that
  recommendation.
- The refactor is behavior-preserving for the legacy PATCH
  endpoint: the same metadata-build call, the same `template.save`
  call, the same `_sync_abandoned_cart_image_config` call, the
  same `_create_version` call (status defaults to `"PENDING"`),
  the same `_notify_integrations` call. Every existing test
  assertion in
  `retail/templates/tests/strategies/test_update_template_strategies.py`
  and
  `retail/templates/tests/usecases/test_update_template_body.py`
  continues to pass without modification.
- The new sample endpoint composes the same helpers but stops
  after `_create_version_with_options` — no `_notify_integrations`
  call. The branch point is at the use case level, not buried
  inside `update_template` behind a flag.
- Constitution Principle IV (Self-Documenting Code, SLAP): each
  helper has a single purpose and a single level of abstraction.
  `update_template` reads as "apply metadata → create version →
  notify integrations" without inline string formatting or
  branching logic.
- The same shape works for `UpdateCustomTemplateStrategy`: the
  custom strategy's `update_template`
  (`retail/templates/strategies/update_template_strategies.py:251-285`)
  has its own additional logic (`parameters`,
  `start_condition`, `variables`) that runs BEFORE
  `_create_version_and_notify`. The new endpoint's gating (FR-002a)
  refuses non-Direct-Send templates upstream — so the new use case
  composes against `UpdateNormalTemplateStrategy` only for v1.
  Custom templates that are Direct Send-eligible would also be
  served by the same helpers; the Custom strategy's extra logic
  runs from `update_template`, not from the helpers, so it's
  preserved on the legacy path and absent on the new path (which
  is correct — custom templates that are Direct Send-eligible
  don't need the rule-engine code generation in the sample-validation
  flow because the operator-supplied parameters never change in a
  sample-validation submission).

**Alternatives considered**:

- *Parameterize `update_template` with a `version_status` keyword
  argument and a `notify_integrations` boolean*: rejected because
  it puts the branch point inside `update_template` behind two
  flags, which (a) violates SLAP (the method becomes
  "do everything except sometimes skip this"), (b) makes the
  legacy PATCH endpoint's behavior implicit in the default
  argument values, and (c) couples the new endpoint to the legacy
  endpoint's call graph (the new endpoint would call
  `update_template(version_status="APPROVED", notify_integrations=False)`
  — confusing). Extracting helpers and composing them at the
  use-case level is cleaner.
- *Introduce a new strategy subclass
  `SampleValidatedTemplateStrategy(UpdateNormalTemplateStrategy)`
  that overrides `update_template`*: rejected because the
  strategy class's purpose is to encapsulate "how to update a
  template" — but the sample endpoint's behavior is "how to
  conditionally apply an update" which is one layer up from
  "how to update". The strategy-pattern indirection adds nothing
  here; the use case is the right layer to orchestrate the
  conditional + the orchestration.
- *Duplicate the body of `update_template` into the new use case,
  modified to skip the push*: rejected because it forks
  metadata-build / S3-upload / version-create logic into two
  call sites that must stay in lockstep (US2 / Constitution
  Principle IV's coupling concern). Extracting the helpers keeps
  one source of truth for each step.

---

## Decision 5 — `MetaService.submit_template_sample` propagates rather than swallows

**Decision**: The new `MetaService.submit_template_sample(waba_id, sample_body)`
method PROPAGATES `CustomAPIException` (from the client) and any
unexpected exception to its caller, instead of catching, logging,
and returning `None`. The use case catches at a single point and
translates the exception into the domain exception
`MetaSampleUnavailableError` (carries the original HTTP status code,
Meta error code, Meta error message). The view catches the domain
exception and emits HTTP 502 per FR-007b.

**Rationale**:

- Per FR-005c the HTTP 502 response body MUST carry a
  `meta_response` field with the raw Meta error envelope so the
  frontend can display Meta's exact answer to the operator (US3
  AS2). The existing swallow-to-`None` pattern collapses error
  context to a single sentinel; reconstructing the error context
  from log lines or by re-calling Meta is brittle and wasteful
  (it would double-charge the sample quota — spec.md A6 notes
  the Meta sample API has a finite quota envelope).
- The propagation is bounded: it crosses ONE layer (Service →
  Use Case) and is caught at the use case's exception boundary.
  The Constitution Principle I guidance "Services swallow
  infrastructure errors and return `None` on failure" is observed
  in spirit: the raw `requests.exceptions` envelope does NOT
  cross more than one layer; the use case catches
  `CustomAPIException` (the project's own exception type) and
  translates it to the domain `MetaSampleUnavailableError` before
  re-raising to the view.
- The existing `MetaService.fetch_library_template_by_name_and_language`
  (which swallows) has a different contract: its caller treats
  `None` as "fall through to the next strategy", so the error
  context is not needed. The new method's caller has a different
  contract — the error context IS the response — so the swallow
  doesn't fit.
- This is recorded as Complexity Tracking row 1 in plan.md so the
  deviation is visible in code review.

**Alternatives considered**:

- *Make the service swallow to `None` and have the use case
  re-call Meta on `None`*: rejected because it (a) double-charges
  the sample-API quota for every Meta-side failure and (b)
  double-charges p99 latency on every failure path. Meta's
  `2388341 — Samples API Access is restricted` error in particular
  is the very condition we need to surface — a re-call on a
  restricted account would get the same error AND consume one
  more sample slot.
- *Make the service swallow to `None` and have the use case parse
  the most recent log line for context*: rejected because (a)
  log-replay parsing tightly couples the use case to the
  Service's log format (any log-format change breaks the use
  case), (b) log lines from concurrent requests would interleave
  and the use case might parse the wrong line, and (c) the
  pattern is generally considered a code smell.
- *Introduce a result-type wrapper
  `MetaSampleResult(Ok(body) | Err(error_envelope))`*: rejected
  for v1 because the project does not use result-type patterns
  anywhere else, and introducing one for a single method would
  set an inconsistent precedent. The simpler "propagate the
  exception" pattern matches the project's existing exception
  handling idiom (DRF exceptions raised in the use case, caught
  in the view).

---

## Decision 6 — Translator module location and purity

**Decision**: A new pure-function module at
`retail/templates/adapters/direct_send_sample_translator.py`
exposes the entry point:

```python
def build_meta_sample_body(
    dto: ValidateTemplateSampleDTO,
    *,
    resolved_header_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert the validated DTO into the Meta message_samples wire
    shape. Pure — no DB access, no I/O. The use case resolves any
    base64 → S3 URL for IMAGE headers BEFORE calling this function
    (passed in via resolved_header_url) so this stays I/O-free."""
```

The translator dispatches on the payload shape (body-only →
`type: text`; CTA URL button → `type: interactive` /
`interactive.type: cta_url`; reply buttons → `type: interactive` /
`interactive.type: button`) per FR-004 / FR-004a / FR-004b /
FR-004c. It substitutes `{{N}}` placeholders BEFORE assembling the
wire body using `substitute_template_variables` from
`retail.agents.domains.agent_webhook.services.direct_send_payload_builder`
(FR-004e / A7).

**Rationale**:

- Constitution Principle I + FR-004d pin the translator to a
  pure-function module: no DB access, no I/O, testable without
  database setup. Co-locating with the existing
  `template_library_to_custom_adapter.py` matches the file-layout
  convention.
- Reusing `substitute_template_variables` from the dispatch path
  keeps a single source of truth for the substitution semantics
  (US2 / A7's "the LOCAL persisted metadata MUST retain raw
  `{{N}}` placeholders so the dispatch-time renderer can
  re-substitute" guarantee). If we re-implemented substitution
  here, the two implementations could drift and the outbound
  sample would render differently from the actual broadcast.
- Co-located with the templates module: the translator is
  template-content-specific, not broadcast-specific. Putting it
  next to the existing `template_library_to_custom_adapter.py`
  keeps the file structure consistent.
- The `resolved_header_url` parameter accepts the S3 URL for
  IMAGE headers AFTER the use case has uploaded the base64 blob
  (per A9). This keeps the translator I/O-free without forcing
  the caller to mutate the DTO.

**Alternatives considered**:

- *Place the translator next to `direct_send_payload_builder.py`
  in `retail/agents/domains/agent_webhook/services/`*: rejected
  because the translator is part of the template-content-validation
  flow, not the broadcast-dispatch flow. The `agent_webhook`
  module owns dispatch-time rendering; this module owns
  template-content sample validation. Different responsibilities,
  different homes.
- *Inline the translator into the use case as a private method*:
  rejected because FR-004d requires pure-function testability
  without DB setup. Inlining would force every translator test
  to instantiate the use case with mocked dependencies, which
  obscures the unit-of-test (the translator's wire-shape logic).
- *Duplicate `substitute_template_variables` into the translator
  module to remove the cross-module import*: rejected because
  duplication risks drift (US2's lockstep guarantee). The
  cross-module import is small and unidirectional (translator
  imports from broadcast services, not the other way around) —
  no circular dependency concern.

---

## Decision 7 — Audit log shape, event-name enumeration, and PII redaction

**Decision**: Every log line from this endpoint follows
`[TemplateSampleValidation] <event_name>: <key=value> <key=value> ...`
with the closed enumeration of `event_name` tokens pinned by
FR-008a. The format mirrors spec 003's
`[DirectSendCategoryWebhook]` channel exactly — same `[TAG]
event_name: k=v` structure, same log-level discipline, same
single-emission-point pattern (every emission routes through a
private `_emit` helper that bakes in the tag and the format). PII
redaction (FR-008c) is enforced inside the `_emit` helpers — they
log content lengths and presence flags rather than verbatim values.

**Rationale**:

- Spec 003's `[DirectSendCategoryWebhook]` audit log is the local
  precedent for the `[TAG] event_name: k=v` format
  (`retail/webhooks/templates/usecases/direct_send_category.py:251-273`).
  Reusing the same shape means operators can apply the same
  Datadog / Kibana dashboard filters to both channels and the
  same `[TAG]` queries surface both feeds.
- Routing every emission through a single `_emit` helper (FR-009
  precedent in spec 003) enforces the format structurally —
  there's no path by which a contributor can write a malformed
  log line.
- PII redaction (FR-008c) is a new concern this feature
  introduces — the existing webhook (`[DirectSendCategoryWebhook]`)
  logs payload values verbatim because they're not customer-facing
  (`template_category` values are operator-controlled enum tokens
  from Meta). The new endpoint's payload IS customer-facing draft
  content — body text, header text, button labels — which an
  operator hasn't approved yet and may not want logged. The
  emit-time helper redacts to lengths + presence flags for these
  fields; identifiers (UUIDs) are logged verbatim because they're
  operationally needed and carry no customer-facing meaning.

**Alternatives considered**:

- *Use the legacy unprefixed free-form `logger.info(f"...")`
  pattern (`TemplatesStatusWebhook`'s legacy style)*: rejected
  for the same reason spec 003 rejected it (Clarifications
  session 2026-05-24, Pattern A): unprefixed lines don't have a
  stable dashboard-filter token, force every dashboard query to
  pattern-match across the message body, and aren't extensible
  to k=v context fields without re-parsing the message string.
- *Log content verbatim (no PII redaction)*: rejected because
  the endpoint's input is operator-supplied draft content for
  customer-facing messages. Operators may not want their drafts
  appearing in log search results before they've been approved
  (a draft that mentions a customer's name or a campaign code
  could leak via log access). The redaction is cheap (length +
  presence flag) and preserves the operational debuggability
  (you can still see "the operator submitted a 200-char body
  with no header and one URL button").
- *Use structured JSON logging (`logger.info("...", extra={...})`
  with a JSON formatter)*: rejected for v1 because the project's
  existing log infrastructure uses plain f-string logs with the
  `[TAG] event_name: k=v` convention. Switching to structured
  JSON logs is a repo-wide refactor that doesn't belong in this
  feature's PR. Spec 003's `[DirectSendCategoryWebhook]` channel
  uses the same plain-f-string format and operates well at scale.

---

## Decision 8 — No transaction wrapping for the local update

**Decision**: The use case does NOT wrap the
metadata-rewrite + version-create + current_version-advance writes
in `@transaction.atomic` or equivalent. Each write is a single-row
operation under Django's default per-statement transaction
isolation.

**Rationale**:

- The three writes are sequenced as: (1) `INSERT INTO templates_version`
  via `_create_version`, (2) `UPDATE templates_version SET status =
  'APPROVED' WHERE id = <new>` via the explicit save inside
  `_create_version_with_options` (when `status != "PENDING"`),
  (3) `UPDATE templates_template SET metadata = ..., current_version_id = <new>`
  via `_apply_metadata_update` + the explicit save in
  `_create_version_with_options`. Each of these is a single-row
  write; Postgres' implicit row-level locking serializes them
  against any concurrent write to the same template.
- Failure modes are bounded: if (1) fails the metadata write
  hasn't happened (no orphan), the operator retries safely; if
  (2) fails the new Version row exists with `status = "PENDING"`
  (the system's default state — not harmful, just a stale Version
  row that the next sample-validation submission will replace);
  if (3) fails the new Version exists with `status = "APPROVED"`
  but `current_version` still points at the old row — the next
  dispatch reads the old row (safe: dispatches use OLD content,
  not corrupted), and the next sample-validation submission can
  re-fix the pointer. None of these failure modes corrupt
  operator-facing state.
- Wrapping in `@transaction.atomic` would add infrastructure
  overhead (savepoint creation, lock-holding window extension)
  for a workflow that's already idempotent at the operator level
  (US3's retry contract — A6).

**Alternatives considered**:

- *Wrap the three writes in `@transaction.atomic` to guarantee
  all-or-nothing semantics*: rejected because (a) the partial-write
  failure modes are operationally safe (dispatch reads old
  content, not corrupted state), (b) the operator-retry contract
  (US3) already absorbs failure recovery, and (c) holding the
  exclusive row lock across three writes extends the contention
  window for concurrent operators editing the same template.
- *Wrap only writes (2) + (3) in `@transaction.atomic` to keep
  `current_version` consistent with `Version.status`*: rejected
  for the same operational-safety reason — `current_version`
  pointing at a `PENDING` Version is a real state in the system
  (it happens whenever the legacy PATCH endpoint fires) and is
  not corrupted; the dispatch path handles it correctly via the
  status check.

---

## Decision 9 — Substitution source: `template_body_params` only

**Decision**: The variable substitution for the outbound Meta
sample uses `template_body_params` (a positional list mapped to
`{{1}}`, `{{2}}`, ...) as the SOLE source. The `parameters` field
(used by custom templates for rule-engine inputs) is NOT consulted
for substitution; it is passed through to the metadata-build
helper for its existing role.

**Rationale**:

- `template_body_params` matches the contract the existing Direct
  Send broadcast renderer uses for substitution
  (`Broadcast.build_direct_send_message` reads `template_variables`
  keyed by string indices — positional). Using the same source for
  the outbound sample keeps the rendered Meta-side body byte-for-byte
  identical to what the eventual broadcast would render (modulo
  the dispatch-time `template_variables` values, which would
  differ per-contact but follow the same positional indexing).
- `parameters` is a key-value structure (`{name: <str>, value:
  <json>}`) used by `UpdateCustomTemplateStrategy` to feed the
  rule-engine code generator. It doesn't map cleanly to positional
  `{{N}}` placeholders, and substituting it would muddle two
  unrelated input shapes.
- Spec.md A7's substitution rule is OUTBOUND-ONLY. The LOCAL
  persisted `metadata.body` keeps raw `{{N}}` placeholders, so
  the dispatch-time renderer can re-substitute against
  per-contact values. Using the same source on both paths
  (`template_body_params` on the sample-validation outbound,
  `template_variables` on the dispatch outbound) keeps the
  substitution semantics aligned.

**Alternatives considered**:

- *Allow `parameters` to feed the substitution as well*: rejected
  because `parameters` is dict-shaped, not list-shaped — there's
  no positional mapping from `parameters[i].value` to `{{N}}`.
  Forcing one would introduce an arbitrary ordering convention
  that the dispatch-time renderer doesn't share.
- *Introduce a new `sample_variables` field on the request body*:
  rejected because (a) it adds a new required field, breaking
  FR-003's "no new required fields" rule and FR-014's
  request-shape parity guarantee, and (b) the existing
  `template_body_params` already serves this purpose.
- *Skip substitution entirely on the outbound (let Meta see
  `{{1}}` in the body)*: rejected per the updated A7 — Meta's
  classifier would evaluate placeholder-laden skeleton text and
  likely classify as low-quality boilerplate. The whole point of
  the sample-validation flow is to get a verdict that reflects
  what end users will actually receive.

---

## Decision 10 — Response wrapper shape

**Decision**: The HTTP 200 response body is a wrapper object with
exactly four keys (FR-007 / FR-007a):

```jsonc
{
  "category": "UTILITY"          // string — Meta's verdict verbatim
  "template_updated": true,      // bool — whether the local update fired
  "template": {                  // ReadTemplateSerializer-shaped object
    // ... same fields ReadTemplateSerializer produces today
  },
  "meta_sample_response": {      // dict — raw JSON body Meta returned
    "success": true,
    "category": "UTILITY"
  }
}
```

On non-UTILITY verdicts (`MARKETING`, `AUTHENTICATION`, or any
future value Meta may introduce) the `template` key contains the
UNCHANGED template (the frontend can confirm visually no edit was
applied), `template_updated` is `false`, and
`meta_sample_response` carries Meta's body verbatim.

On HTTP 4xx / 5xx error responses the body shape differs (FR-007b
/ FR-007c / FR-007d / FR-007e) — it carries
`{"detail": ..., "error_code": ..., "meta_response": <optional>}`.

**Rationale**:

- FR-007 pins this shape explicitly. The four-key wrapper lets the
  frontend (a) substitute `template` directly into its display
  state without re-fetching (SC-005), (b) display Meta's exact
  verdict to the operator via `meta_sample_response` for
  transparency (US4 AS2), and (c) distinguish "edit applied" from
  "edit not applied" via the `template_updated` boolean without
  re-comparing `template.metadata` against the prior state.
- The error-response shape (FR-007b–e) uses
  `{detail, error_code, [meta_response]}` because it carries no
  `Template` object (the template wasn't fetched or wasn't
  updated). The `error_code` is a stable token the frontend can
  switch on (e.g. show "Template not eligible for Direct Send,
  use the PATCH endpoint" for `not_direct_send_eligible`).

**Alternatives considered**:

- *Return just `ReadTemplateSerializer.data` like the PATCH
  endpoint does*: rejected because the operator needs to see
  Meta's verdict ("UTILITY" / "MARKETING") to make an informed
  decision on the next edit. Without the wrapper the operator
  would have to re-fetch the template to see if metadata changed
  — defeating SC-005.
- *Use HTTP 422 for non-UTILITY verdicts to signal "edit
  rejected"*: rejected because the request itself succeeded
  (Meta classified it, we processed the response). The
  non-UTILITY outcome is a normal business outcome, not a
  request error. HTTP 200 with `template_updated: false` is the
  right semantic.
- *Inline the `meta_response` body as top-level fields on the
  wrapper*: rejected because Meta's response shape may evolve
  (new categories, additional metadata) and embedding the raw
  body under one key isolates Retail's wrapper from Meta-side
  schema drift.
