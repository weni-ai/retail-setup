# Implementation Plan: WhatsApp Direct Send Broadcasts (OrderStatus)

**Branch**: `002-direct-send-broadcasts`
**Date**: 2026-05-20
**Spec**: [./spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-direct-send-broadcasts/spec.md`

## Summary

Wire the OrderStatus agent to WhatsApp's Direct Send Beta so that
Retail performs template variable substitution on its side and
dispatches a fully-substituted message to the messaging gateway
(Flows) without relying on a Meta-side template-approval cycle. This
removes the Integrations-engine template-creation step from the
OrderStatus assignment flow whenever the project's WhatsApp channel
reports `direct_send=true`, persists the templates locally with
content fetched from Meta's library catalog (in the project's
VTEX-resolved locale, with a per-template `pt_BR` fallback), and
routes broadcasts through a new `direct_send: true` payload shape.
Two new `Version.status` values (`PAUSED`, `FLAGGED`) are introduced
as broadcast-disabling states. All legacy behavior is preserved
bit-for-bit when the channel does not have Direct Send enabled
(majority of Beta-period traffic).

The technical approach (resolved in `./research.md`) is:

1. Set the Direct Send flag inside the existing `IntegratedAgent.config`
   JSONField at agent-assignment time
   (`agent.config["direct_send"] = ...; agent.save(update_fields=["config"])`)
   from `IntegrationsService.get_channel_app("wpp-cloud", app_uuid)`'s
   `config.direct_send` boolean. Reads use
   `agent.config.get("direct_send", False)` so absence of the key
   defaults to `False` — matching FR-005 ("channel reports Direct
   Send disabled or the lookup fails → legacy path"). No new column
   is added to `IntegratedAgent` and no migration ships against the
   agents app for this feature (data-model.md §1 Decision).
2. Branch `AssignAgentUseCase._create_library_templates` on
   `IntegratedAgent.direct_send`: when `True`, fetch each template
   from Meta's library catalog via a new
   `MetaService.fetch_library_template_by_name_and_language(name, language)`
   in the project-resolved locale (read from
   `integrated_agent.config["initial_template_language"]`, defaulting
   to `DEFAULT_TEMPLATE_LANGUAGE = "pt_BR"` imported from
   `retail.agents.shared.country_code_utils` — already used by
   `AssignAgentUseCase._build_initial_config`), with a `pt_BR`
   per-template fallback, persist the local Template+Version with
   content + `status="APPROVED"`, and skip the Integrations-engine
   submission. The whole flow runs inside the existing
   `@transaction.atomic execute(...)`. The shared adapter
   (`adapt_meta_library_template_response`) normalizes the upstream
   payload at the service boundary per FR-003e (plain-string `header`
   → `{header_type: "TEXT", text: <string>}`), FR-003f (strict
   rejection of `PHONE_NUMBER` / `PAYMENT_REQUEST` / `ORDER_DETAILS`
   / `COPY_CODE` / `FLOW` button types; dual URL-button shape
   normalization), and the Session 2026-05-22 Q3 drop-rule (auxiliary
   curation fields `body_param_types` / `attributes` / `topic` /
   `usecase` / `industry` / `id` MUST be dropped at fetch time). All
   four rejection branches (header shape, button type, length / count
   overflow, malformed JSON) raise
   `DirectSendUnsupportedComponentError`; the use case routes the
   exception through FR-003c (pt_BR retry) and then FR-003d (atomic
   rollback) so the operator-facing outcome stays uniform — see
   `data-model.md §5` ("Adapter normative behaviour") and the
   `Post-design spec updates folded in` sub-section of §Constraints
   below.
3. Extend `Version.STATUS_CHOICES` with `PAUSED` and `FLAGGED`. Tighten
   the existing single dispatch gate at
   `Broadcast.get_current_template` so that `PAUSED`/`FLAGGED` versions
   produce an explicit audit-log entry on top of the existing
   "non-APPROVED → skip" semantics.
4. Add `Broadcast.build_direct_send_message` that (a) looks up the
   local Template's metadata, (b) substitutes `{{N}}` placeholders
   with the Lambda's `template_variables` dict, (c) emits the new
   `msg.direct_send=true` payload shape (see
   `./contracts/messaging-gateway-payload.md`). Route between this
   builder and the legacy `build_broadcast_template_message` based
   on `IntegratedAgent.direct_send`.
5. Validate the local template name against `^[a-z0-9_]+$`/512 chars
   before sending; skip with audit-log entry on violation (the
   OrderStatus agent's templates already comply, so this is
   defensive).

## Technical Context

**Language/Version**: Python 3.10 (`pyproject.toml` `python = "^3.10"`).

**Primary Dependencies**: Django 5.0, Django REST Framework 3.15,
Celery 5, weni-eda 0.1.1, requests (via `RequestClient`), babel,
phonenumbers, weni-datalake-sdk 0.5.0, Sentry SDK 2, Elastic APM 6.

**Storage**: PostgreSQL via `psycopg2`. The only schema change is a
new enum value pair (`PAUSED`, `FLAGGED`) on `templates_version`; no
column is added to `agents_integratedagent` (the Direct Send flag
lives inside its existing `config` JSONField — see
`./data-model.md §1`). No new tables.

**Testing**: `django.test.TestCase` + `unittest.mock`
(`MagicMock(spec=...)` for service interfaces, `patch` at the HTTP
client boundary). `coverage` 7.8 + the project's
`contrib/compare_coverage.py` parity check.

**Target Platform**: Linux (containerized service, `docker/`).

**Project Type**: web-service (Django + DRF backend behind an OIDC
gateway + internal HTTP API consumed by Flows / Integrations).

**Performance Goals**:

- Order-status webhook hot path: no new outbound HTTP call (Meta
  is consulted at assignment time only). Existing p95 baseline
  (~300ms) must be preserved.
- Agent assignment: at most one Meta library-catalog GET per
  pre-approved template per assignment in the Direct-Send branch
  (and at most one extra GET per template if the `pt_BR` fallback
  fires). Assignment p95 may grow by `N × meta_p95` where `N` is
  the number of OrderStatus pre-approved templates (4 in the
  current dataset).

**Constraints**:

- **Legacy-path preservation (Story 4 — FR-015, FR-020, FR-021,
  FR-027, SC-004, SC-007, SC-008)**:
  - Legacy dispatch payload MUST stay byte-identical with today (per
    the spec's "byte-identical" definition: same keys, same values,
    same types, same array order; key order MAY differ). A snapshot
    test (`retail/agents/tests/services/test_broadcast_legacy_payload.py`
    — `tasks.md` T033) pins the exact request body for body-only,
    image-header-with-CTA-URL, and image-header-with-payment-buttons-
    plus-`order_details` template combinations the OrderStatus
    fleet exercises today.
  - Legacy outbound calls to the Integrations service
    (`fetch_templates_from_user`, `notify_integrations`,
    `create_template_message`, `create_template_translation`,
    `create_library_template_message`) MUST keep their current
    signatures, payloads, and retry semantics. The assignment-flow
    snapshot test (`tasks.md` T034) pins the exact arguments.
  - The existing datalake event payloads (`weni_datalake_sdk` /
    `CommerceWebhookPath`) are emitted with the same keys and value
    types on the legacy path. No new field is added on the legacy
    emission.
  - The existing log-line shape for "skipped due to non-`APPROVED`
    current version" MUST be preserved bit-for-bit on the legacy
    path. The new `[BroadcastDispatch] skipped_due_to_status: ...`
    shape introduced for `PAUSED` / `FLAGGED` is a disjoint prefix so
    consumers that route on the legacy shape are unaffected.
  - The existing Sentry / Elastic APM tags on the dispatch span MUST
    NOT be renamed or removed. An optional `direct_send` tag MAY be
    added; on the legacy path it is omitted (or set to `False`) so
    existing dashboards continue to work unchanged.

- **Public-surface preservation (FR-021, FR-022)**:
  - Existing model fields on `IntegratedAgent` (`uuid`, `channel_uuid`,
    `agent`, `project`, `is_active`, `ignore_templates`,
    `contact_percentage`, `config`, `global_rule_code`,
    `global_rule_prompt`, `parent_agent_uuid`, `created_on`,
    `broadcasts_delivered`), on `Template` (`uuid`, `name`, `parent`,
    `current_version`, `rule_code`, `integrated_agent`, `metadata`,
    `needs_button_edit`, `deleted_at`, `is_active`, `start_condition`,
    `display_name`, `variables`, `config`), and on `Version`
    (`template`, `template_name`, `integrations_app_uuid`, `project`,
    `status`, `created_at`, `uuid`) are preserved as-is.
  - The only model-level changes are: (a) two additive values
    appended to `Version.STATUS_CHOICES` (`PAUSED`, `FLAGGED`);
    (b) an additive optional sub-object `direct_send` inside
    `Template.metadata`, present only on Direct-Send-path templates.
    The Direct Send flag itself adds NO new column to
    `IntegratedAgent` — it is stored as an optional key
    (`direct_send: bool`) inside the existing `IntegratedAgent.config`
    JSON, with absence interpreted as `False` (data-model.md §1
    Decision).
  - Existing keys inside `IntegratedAgent.config`
    (`initial_template_language`, `country_phone_code`,
    `abandoned_cart`, `payment_recovery`, `integration_settings`,
    `delivered_order_tracking_config`) are preserved as-is. The
    feature adds one new optional key `direct_send: bool` to
    `IntegratedAgent.config` (absence interpreted as `False`) —
    purely additive within the JSON; no existing key is renamed or
    removed (data-model.md §1). The upstream `Agent` and
    `PreApprovedTemplate` models are also untouched.
  - Existing fields on `ReadIntegratedAgentSerializer` (`uuid`,
    `channel_uuid`, `templates`, `webhook_url`, `description`,
    `contact_percentage`, `global_rule_prompt`,
    `initial_template_language`, `delivered_order_tracking_config`,
    `has_delivered_order_templates`, `abandoned_cart_config`) are
    preserved as-is. Adding the read-only `direct_send` field
    (`tasks.md` T028) is purely additive per the spec assumption that
    downstream consumers ignore unknown JSON fields; the field is
    computed at serialization time from
    `obj.config.get("direct_send", False)` so the wire shape is
    unchanged from US1's first implementation while the underlying
    storage moved from a column to the existing `config` JSON
    (data-model.md §1 Decision).
  - No URL path, HTTP method, required header, or required query
    parameter is renamed or removed. No new required field is added
    to any inbound payload (order-status webhook, agent-assignment,
    send-test-template, template-status webhook). Inbound contracts
    referenced: `contracts/integrations-channel-app.md` for the
    channel-app GET, plus the existing project endpoints unchanged
    by this feature.

- **Hot path & deploy safety**:
  - The dispatch hot path MUST NOT call Meta (FR-003a Assumption).
  - The assignment use case MUST stay `@transaction.atomic`. A
    failure to fetch a required template (after the `pt_BR` fallback)
    MUST roll back every persisted row (FR-003d).

- **Settings & env (FR-024)**: No new environment variable or
  settings key. The feature reuses the env vars `ORDER_STATUS_AGENT_UUID`,
  `WHATSAPP_API_URL`, `META_VERSION`, `META_SYSTEM_USER_ACCESS_TOKEN`,
  `INTEGRATIONS_REST_ENDPOINT` (the derived Django attribute
  `settings.META_API_URL = urljoin(WHATSAPP_API_URL, META_VERSION)`
  is read by `MetaClient`; no new env layer is introduced). The
  unrelated existing keys (`ORDER_STATUS_DUPLICATE_WINDOW_SECONDS`,
  `ABANDONED_CART_AGENT_UUID`, `PAYMENT_RECOVERY_AGENT_UUID`,
  `ABANDONED_CART_DEFAULT_IMAGE_URL`, `DOMAIN`) keep their current
  names, types, and defaults. Deploying this feature without any
  settings change is safe.

- **Migration & rollback safety (FR-025, FR-026)**:
  - The feature ships ONE migration only —
    `0017_alter_version_status_paused_flagged` — which appends
    `PAUSED` and `FLAGGED` to `Version.STATUS_CHOICES` at the end of
    the existing tuple; every existing row's status (one of the
    eight pre-existing values) remains valid, no backfill required.
    The migration's `dependencies = [...]` chains to the latest
    existing `templates` migration.
  - The Direct Send flag itself ships NO migration: it is stored as
    an optional key inside the existing `IntegratedAgent.config`
    JSON (data-model.md §1 Decision); absence of the key is
    interpreted as `False`, so legacy rows need no backfill. This is
    the spec correction recorded in `data-model.md §1` (the original
    US1-first-implementation drafted a new `IntegratedAgent.direct_send`
    column; it was relocated to `config["direct_send"]` to collapse
    the rollout footprint to zero schema change on `IntegratedAgent`).
  - The migration is a forward-only `AlterField` operation and is
    reversible by Django's default `migrate <app> <prev>` rollback
    (the `AlterField` reverse operation is auto-generated). Reverting
    only the feature code while leaving the migration applied is
    also safe — the new enum values stay unused once the dispatch
    gate code is removed, and the `config["direct_send"]` key (if
    populated by an in-flight assignment) is read as `False` by the
    reverted code, falling back onto the legacy path
    (`quickstart.md` §9 covers the operator-facing rollback procedure
    end-to-end).

- **Post-design spec updates folded in (Session 2026-05-22 —
  FR-003e, FR-003f, auxiliary-field drop)**: three normative
  clarifications were appended to `spec.md` AFTER this plan's
  initial design pass and AFTER the original implementation closed
  out (Phase 7 T036–T039 marked `[X]` on 2026-05-21). They are
  restated here so the plan stays self-contained for review and so
  the merge gate covers them:

  - **FR-003e — `header` plain-string + canonical normalization**:
    Meta's library catalog ALWAYS returns `header` either absent or
    as a plain text string (NEVER as a dict). The fetch-time
    adapter (`adapt_meta_library_template_response` in
    `retail/templates/usecases/_meta_library_template_fetch.py`)
    MUST accept `header` only when absent or a string,
    length-validate it against `MAX_HEADER_TEXT_LENGTH`, and
    normalize the persisted form to
    `Template.metadata.header = {header_type: "TEXT", text: <string>}`
    — the canonical Retail-internal shape (`data-model.md §3`).
    Any non-string, non-null `header` raises
    `DirectSendUnsupportedComponentError` so the use case routes
    through FR-003c → FR-003d. Image / media headers on Direct
    Send-path Templates arise EXCLUSIVELY from post-assignment
    edits to `Template.metadata.header.header_type` via the
    `update_template` endpoint (FR-026); the dispatch path
    (`Broadcast.build_direct_send_message` →
    `direct_send_payload_builder.build_direct_send_header`)
    continues to honour both `TEXT` and `IMAGE` header types
    unchanged from US1. The contract artifact
    `contracts/meta-library-catalog.md §2 / §5` previously showed
    `header` as a dict; both sections have been corrected to match
    FR-003e (the spec is canonical).
  - **FR-003f — button-type strict rejection + dual URL shape
    normalization**: any `buttons[*].type` outside
    `{URL, QUICK_REPLY}` — including `PHONE_NUMBER`,
    `PAYMENT_REQUEST`, `ORDER_DETAILS`, `COPY_CODE`, `FLOW`, or any
    future Meta-curated value — MUST be rejected at fetch time by
    raising `DirectSendUnsupportedComponentError`; the use case
    routes through FR-003c → FR-003d. URL-button entries MAY arrive
    with either a flat `url` string OR the legacy nested
    `{base_url, url_suffix_example}` shape; both MUST be normalized
    to a flat `url` string at persist time via the same
    `_ensure_protocol` + `_append_placeholder_if_needed` heuristic
    the push-path `ButtonTransformer` already applies, so
    `metadata.buttons` stores a single canonical shape regardless
    of upstream variance. The fetch-time count limits (≤1 `URL`,
    ≤3 `QUICK_REPLY`) and `MAX_BUTTON_LABEL_LENGTH` (20 chars)
    remain enforced. Post-assignment edits to
    `Template.metadata.buttons` via `update_template` are governed
    by FR-026 and are NOT bound by this fetch-time policy.
  - **Auxiliary-field drop at fetch time (Session 2026-05-22 Q3)**:
    Meta's library-catalog response may carry auxiliary curation
    fields (`body_param_types`, `attributes`, `topic`, `usecase`,
    `industry`, `id`). The adapter MUST drop all of them — only
    the dispatch-relevant subset
    `{header, body, body_params, footer, buttons, category,
    language}` is propagated to `TemplateInfo.metadata`, alongside
    the `direct_send` audit sub-object that the use case adds at
    write time (`data-model.md §3`). Anti-YAGNI: future features
    that need AMOUNT/DATE-aware variable rendering or
    Meta-template-ID correlation will be free to extend
    `metadata.direct_send` additively rather than ingesting unused
    fields preemptively.

  These three rules use the pre-existing
  `DirectSendUnsupportedComponentError` exception (T007) so no new
  exception type is introduced. Their fold-in is tracked as
  `tasks.md` Phase 8 (T107–T111) and applies retroactively to US2's
  adapter implementation (T023). If a future PR ever needs to
  loosen any of the three rules, the spec edit MUST be reflected
  here in the same PR; if this section and `spec.md` ever disagree,
  the spec wins.

- **Template-status webhook (FR-023)**: The existing template-status
  webhook handler is not touched by this feature. The future feature
  that delivers Meta's `PAUSED` / `FLAGGED` events will register the
  mapping; this feature only ensures the local enum can hold the
  values when that future feature lands. No new Integrations Engine
  subscription is required at deploy time.

- **Idempotency & retry safety (Story 1, Story 2 — FR-028 through
  FR-039, SC-009)**:

  > **Source**: `spec.md` §Idempotency & retry safety is the single
  > source of truth for the normative claims below. The bullets in
  > this section restate the spec's tuple, retry-budget, dedup-cache,
  > and audit-log catalogue with implementation-specific anchors
  > (file paths, line ranges, env-var names) so the plan stays
  > self-contained for design review. A future spec edit to FR-028 /
  > FR-029 / FR-034 / FR-039 etc. MUST be reflected here in the same
  > PR; if the spec and this section ever disagree, the spec wins.

  - **Canonical idempotency tuple**: `(Project,
    IntegratedAgent.uuid, OrderStatusDTO.orderId,
    OrderStatusDTO.currentState)` (spec FR-028 / "Single logical
    broadcast"). The `Project` component is serialized as
    `IntegratedAgent.project_id` (the FK integer) in the current
    cache-key string for compactness; serializing as `Project.uuid`
    is also spec-compliant per FR-028's serialization rule. This is
    the dedup key for the order-status webhook AND the definition of
    "single logical broadcast" for the Exactly-Once Dispatch
    invariant. The same key is implemented as a Django cache key in
    `_is_duplicate_event` at
    `retail/agents/domains/agent_webhook/usecases/order_status.py:181-211`.
  - **Dedup cache backend**: Django's default cache backend
    (`django.core.cache.cache`) — Redis in staging and production,
    LocMemCache under tests via
    `@override_settings(CACHES={"default": {"BACKEND":
    "django.core.cache.backends.locmem.LocMemCache"}})`. The
    `cache.add` semantics rely on the backend's atomic SETNX (Redis)
    or per-process dict-update (LocMem); both satisfy "at most one
    worker observes event_registered_now == True" within the dedup
    window.
  - **Dedup cache failure mode**: fail-CLOSED. If the cache backend
    is unreachable, `cache.add` raises and the order-status entry
    point propagates the error — the trigger fails fast, no
    `BroadcastMessage` is persisted, no Flows POST is issued. This is
    the conservative default per FR-028 / Edge Cases. Switching to
    fail-OPEN ("allow dispatch on cache outage, accept possible
    duplicate") is a spec change, not a code change.
  - **Dedup window length**: `ORDER_STATUS_DUPLICATE_WINDOW_SECONDS`,
    default 60s (`retail/settings.py:344`). Operational tuning per
    FR-029.
  - **Retry budget = 0 on the dispatch hot path**: Retail does not
    originate retries from
    `AgentOrderStatusUpdateUsecase.execute` / `Broadcast.send_message`
    / `_record_broadcast_message`. A Flows 5xx surfaces as
    `BroadcastMessage.status=FAILED` via `_record_failed_dispatch`
    and the original exception is re-raised — there is no
    in-process retry loop. Retry safety on inbound topics
    (`retail.template-send`, `retail.template-status`) is provided
    by the broker's at-least-once delivery + the use case's
    idempotency contract (FR-035), NOT by Retail-side retry logic.
  - **Broker (RabbitMQ) delivery semantics**: at-least-once,
    consumer-acks-after-use-case. `BroadcastConsumer.consume`
    (`retail/broadcasts/consumers/broadcast_status_consumer.py:48`)
    calls `self.ack()` only after the use case method returns
    successfully; a crash before that line triggers a redelivery.
    The use case methods (`link_send_event`, `apply_status_event`,
    `MarkBroadcastConvertedUseCase.execute`) are idempotent against
    redelivery (FR-035, FR-036).
  - **Celery retry policy**: every Celery task in the OrderStatus
    pipeline is one-shot. The project's Celery instance
    (`retail/celery.py`) uses default settings — `task_acks_late=False`
    (early-ack) and no explicit `task.retry(...)` calls inside the
    OrderStatus tasks (`task_order_status_update`,
    `task_mark_broadcast_converted`, `handle_purchase_event_task`
    in `retail/vtex/tasks.py`). Re-delivery comes from either (a)
    the EDA broker (RabbitMQ) re-delivering unacked
    `retail.template-send` / `retail.template-status` messages to
    `BroadcastConsumer.consume`, or (b) the upstream caller
    re-firing the entry-point task. Both routes are absorbed by
    FR-035 / FR-036 idempotency. A poison-message DLX is NOT a v1
    requirement (FR-038); the existing Celery configuration is
    preserved as-is.
  - **Partial-batch results NOT cached at assignment time**:
    `AssignAgentUseCase._create_library_templates` issues a Meta
    library-catalog GET per pre-approved template inside a single
    `@transaction.atomic` block. Successful per-template fetches are
    NOT cached across assignment attempts; an operator-initiated
    retry after FR-003d MUST re-fetch every template from scratch
    (FR-003d, last sentence). This trades a marginally slower retry
    for a guarantee that the persisted snapshot always reflects the
    catalog at retry time (CHK019 of `idempotency.md`).
  - **`BroadcastMessage` persistence keys**: the conditional unique
    constraints `broadcasts_broadcast_id_unique` and
    `broadcasts_external_message_id_unique` (FR-032) are restated as
    requirements; a migration that drops either is a forbidden
    regression. The constraints live on
    `retail/broadcasts/models.py:145-156`.
  - **`BroadcastConversion` persistence key**: the unique constraint
    `broadcast_conversions_project_order_unique` on
    `(project, order_id)` (FR-033) is the exact-once boundary for
    conversion attribution. `MarkBroadcastConvertedUseCase` writes
    via `get_or_create` so a re-delivery converges on the existing
    row without raising.
  - **`IntegratedAgent.broadcasts_delivered`**: incremented exactly
    once per first-DELIVERED transition (FR-034). The `F("…")+1`
    expression is atomic across concurrent transitions; the
    `is_first_delivery` predicate in `_apply_status_transition` is
    what makes it idempotent across broker redeliveries.
  - **Audit log shape catalogue (FR-039)**: six distinct shapes are
    pinned in spec.md FR-039 — five refusal shapes (dedup skip,
    PAUSED/FLAGGED skip, Direct Send validation skip, legacy
    non-APPROVED skip, Direct Send assignment atomic failure) and
    one admission shape (order-status agent resolution). Consumers
    can route on each class independently. The Direct Send-specific
    refusal shape is also pinned by research Decision 7 /
    `tasks.md` T013; the agent-resolution admission shape is pinned
    by `tasks.md` T014b against the existing
    `_lookup_order_status_agent` log line at
    `retail/agents/domains/agent_webhook/usecases/order_status.py:105-108`
    (FR-031).

- **Tenant isolation (Story 1, Story 2, Story 4 — FR-040 through
  FR-046, SC-010)**:

  > **Source**: `spec.md` §Tenant isolation is the single source of
  > truth for the normative claims below. The bullets in this section
  > restate the spec's canonical-tenant-identifier rule, FK-chain
  > scoping, multi-credential surface taxonomy, and per-key cache /
  > observability guarantees with implementation-specific anchors
  > (file paths, line ranges, env-var names) so the plan stays
  > self-contained for design review. A future spec edit to FR-040 /
  > FR-041 / FR-042 / FR-043 / FR-044 / FR-045 / FR-046 MUST be
  > reflected here in the same PR; if the spec and this section ever
  > disagree, the spec wins.

  - **Canonical tenant identifier**: `Project.uuid` (Retail-internal
    UUID). Public identifier emitted in logs, EDA payloads, span
    tags, and API responses. The integer FK `Project.id` is the
    internal storage key used for joins and cache-key compactness;
    both uniquely identify the same row, so any tenant-scoping
    requirement that says "scoped by project" is satisfied by either
    serialization (FR-040). `Project.vtex_account` is the EXTERNAL
    tenant identifier with the documented "duplicate → return None"
    SECURITY BOUNDARY at
    `retail/agents/domains/agent_webhook/usecases/order_status.py:174`.
  - **Tenant FK chain (canonical scoping)**: `BroadcastMessage`,
    `BroadcastConversion`, `IntegratedAgent` carry a direct FK to
    `Project`. `Credential`, `Template`, `Version` chain through
    `integrated_agent.project`. `Version` ALSO has a direct FK to
    `Project` (dual-path scoping) so the dispatch-time queryset at
    `Broadcast.get_current_template`
    (`retail/agents/domains/agent_webhook/services/broadcast.py:602`)
    can filter by project without joining through `Template`. The
    invariant `Template.integrated_agent.project_id ==
    Version.project_id` is the FK-level guarantee that supports
    SC-010 invariants (a) / (c). Spec FR-040 restates this as a
    requirement.
  - **Multi-credential surface taxonomy** (FR §Tenant isolation):
    four credential surfaces, three tenant scopes —
    - `META_SYSTEM_USER_ACCESS_TOKEN` (env var,
      `retail/settings.py`): CROSS-tenant by design, library-catalog
      reads only at agent-assignment time. Justified by the catalog
      being a Meta-curated public resource (see
      `contracts/meta-library-catalog.md` §9). The accepted
      cross-tenant blast radius (a Meta rate-limit on this token
      stalls every project's assignments simultaneously) is
      documented as an Edge Case + a `[Conflict]` resolution in
      `research.md` Decision 16.
    - Channel-side WhatsApp Cloud credentials (PER-tenant): consumed
      at dispatch time via the Flows POST body's `channel` UUID
      (`contracts/messaging-gateway-payload.md` §1, §8). Retail
      never holds the per-channel WABA / phone-number credentials
      directly; Integrations Engine and Flows are the keepers.
    - Flows internal-auth token (CROSS-tenant by design,
      `INTERNAL_FLOWS_TOKEN` / `FLOWS_REST_ENDPOINT`): same Weni
      service-account token used for every project's broadcast
      POST; tenant scoping is enforced by Flows on its side via the
      `project` field in the request body.
    - Per-agent `Credential` rows (DB-backed, PER-tenant): scoped by
      FK chain `Credential.integrated_agent.project`. Consumed by
      Lambda invocation parameters, never logged in plaintext.
  - **Cache key project-scoping (canonical key shapes)**: every
    cache key that materializes tenant-scoped state MUST include a
    project component. The canonical shapes for this feature's
    surface are:
    - `order_status_event:{integrated_agent.project_id}:{integrated_agent.uuid}:{order_id}:{current_state}`
      (order-status dedup, FR-028) —
      `retail/agents/domains/agent_webhook/usecases/order_status.py:199-211`.
      The `project_id` component is the tenant scoping; dropping it
      OR replacing it with a non-globally-unique component (e.g.
      `agent_uuid` alone) is a forbidden regression (FR-040).
    - `project_by_vtex_account_{project.vtex_account}` (project
      resolution by external tenant identifier) —
      `retail/agents/domains/agent_webhook/usecases/order_status.py:159-167`.
    - `project_by_uuid_{project.uuid}` and `project_domain_{project.uuid}`
      (project lookups keyed by canonical tenant identifier) —
      `retail/projects/models.py:38-39`.
    - The `IntegratedAgentCacheHandlerRedis` family
      (`retail/agents/shared/cache.py`) keys agent caches by
      `integrated_agent.uuid`; tenant scoping is transitive via the
      cached row's `project_id`. The cached value MUST be
      invalidated when the project's relevant fields change
      (`Project.clear_integrated_agents_cache`,
      `retail/projects/models.py:43-51`).
  - **Cache failure mode and tenant boundary**: a cache outage that
    causes a stale read on `project_by_vtex_account_{...}` cannot
    cross tenants because the cached value's `Project.uuid` is the
    canonical tenant identifier — a stale-but-valid Project resolves
    to the same tenant it resolved to when cached. The
    `MultipleObjectsReturned → None` security boundary is the
    DB-level fallback when the cache is missed and the DB has
    inconsistent data (FR-041 (d)).
  - **EDA / datalake event tenant tagging**: every outbound event
    on `weni_datalake_sdk` / `CommerceWebhookPath` MUST include
    `project=str(integrated_agent.project.uuid)` (FR-042). The
    pinned audit point is `Broadcast._send_to_datalake`
    (`retail/agents/domains/agent_webhook/services/broadcast.py:743-754`)
    where `event_data["project"] = str(integrated_agent.project.uuid)`
    is the only tenant-key the consumer side reads. The legacy
    datalake snapshot test (`tasks.md` T035a) pins this field's
    presence; a future emission that drops it fails CI.
  - **Inbound EDA consumer tenant resolution**: the supported
    resolution mechanisms (FR-041 (a)–(d)) are pinned to:
    - `BroadcastConsumer.consume`
      (`retail/broadcasts/consumers/broadcast_status_consumer.py:48`)
      → resolves the row via `broadcast_id` (first event) or
      `external_message_id` (subsequent events) — both globally
      unique per the upstream contracts in
      `contracts/messaging-gateway-payload.md` §7.3 / §7.4.
    - `AgentOrderStatusUpdateUsecase.execute`
      (`retail/agents/domains/agent_webhook/usecases/order_status.py:213`)
      → resolves the project via
      `get_project_by_vtex_account(vtex_account)` with the
      "duplicate → None" SECURITY BOUNDARY.
    - Any new EDA consumer added by a future PR MUST justify its
      tenant-resolution mechanism against FR-041 (a)–(d) or extend
      the list with a documented assumption.
  - **Observability tags include `project_uuid`** (FR-044): Sentry
    and Elastic APM spans on the dispatch hot path SHOULD include
    `project_uuid` whenever it is in scope. The legacy preservation
    rule (FR-027) does NOT permit removing existing tags; adding
    `project_uuid` is purely additive and is enforced by the
    legacy-observability snapshot test (`tasks.md` T035b). The
    dispatch use case has the project in scope at every log line
    via `integrated_agent.project.uuid`; the legacy log lines
    already comply (`retail/agents/domains/agent_webhook/services/broadcast.py:622-682`).
  - **Lambda function-name namespace is per-project** (FR-040
    upstream precondition): the per-agent Lambda is invoked by name
    `retail-setup-{hash_13_digits}` where the hash is
    `SHA256(agent.name + agent.uuid.hex)`
    (`retail/agents/domains/agent_management/usecases/push.py:112-123`);
    `Agent.project` is a per-project FK so the function-name
    namespace is per-project by construction. The IAM role attached
    to Retail is scoped so that only function names following this
    naming convention can be invoked. This is the precondition that
    closes the "rule engine for project A invokes project B's
    Lambda" surface; documented as an Assumption in spec.md.
  - **FR-043 v1 implementation status (defense-in-depth follow-up)**:
    The spec's required cross-validation between the `app_uuid`
    query parameter and the `Project-Uuid` header is satisfied at
    v1 transitively through three layers — DRF's `HasProjectPermission`
    on `AssignAgentView` (operator must be a contributor/moderator
    of `Project-Uuid`), Integrations Engine's own authorization on
    `GET /api/v1/apptypes/wpp-cloud/apps/{app_uuid}/` (a
    cross-project read returns 404), and `IntegrationsService.get_channel_app(...)`'s
    fail-closed `None` return on any HTTP error. The explicit Retail-side
    cross-validation (`app.config.project_uuid ==
    request.headers["Project-Uuid"]` with HTTP 403 on mismatch) is
    NOT implemented in this PR; it is captured as a defense-in-depth
    follow-up scoped to a separate `feat/tenant-isolation-cross-validation`
    PR. The trust boundary on Integrations Engine is documented as
    an Assumption in spec.md and pinned in
    `contracts/integrations-channel-app.md` §9.
  - **Runtime invariant audit (SC-010 measurement)**: the SQL audit
    query for invariant (a) (`BroadcastMessage.project_id ==
    BroadcastMessage.integrated_agent.project_id`) is materialized
    in the test suite as `tasks.md` T035c — a Django `TestCase` that
    seeds two projects, dispatches a broadcast in each, and asserts
    that no `BroadcastMessage.project_id` value crosses to the
    wrong `IntegratedAgent.project_id`, plus secondary assertions
    on the dedup cache key (FR-040), the datalake event payload
    (FR-042), and the per-IntegratedAgent template lookup (FR-045).
    Invariants (b)–(d) are structurally guaranteed by FK constraints
    (the Django ORM raises `IntegrityError` at write time) and are
    spot-checked by integration tests under
    `retail/broadcasts/tests/test_models.py`. A Django middleware /
    queryset wrapper that asserts tenant scoping at every read is
    OUT OF SCOPE for v1 — the audit query + the FK constraints +
    code review are the merge gate. Stating the gate is the
    requirement (FR-040 last sentence).

- **PR coverage cannot decrease** (Constitution Principle III).

**Scale/Scope**:

- Active OrderStatus integrations: ~hundreds of projects today
  (Beta access is being rolled out gradually per WABA).
- Order-status broadcasts: 50–200 dispatches/sec at peak across the
  fleet. The Direct-Send subset is a fraction of that during Beta.
- Code surface: ~10 files modified, ~4 new files (one new test
  file per new module). No new app, no new endpoint.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1
design. Reference: `.specify/memory/constitution.md` (v1.0.0).*

### I. Layered Clean Architecture (NON-NEGOTIABLE) — PASS

The plan introduces no view-side queries, no use-case-side DRF
imports, and no infrastructure exception leaks past the Service
layer.

- New use-case work lives entirely under
  `retail/agents/domains/agent_integration/usecases/` (assignment
  branch), `retail/agents/domains/agent_webhook/services/`
  (broadcast builder), and `retail/templates/usecases/`
  (Meta-library helper).
- The new `MetaClient.fetch_library_template_by_name_and_language`
  is the only outbound HTTP call introduced; it is a Client (the
  only layer allowed outbound HTTP per Principle I).
- The new `MetaService.fetch_library_template_by_name_and_language`
  swallows infrastructure exceptions and returns `None` (Principle I
  Service contract).
- The new `Broadcast.build_direct_send_message` is on the existing
  `Broadcast` Service-equivalent class and contains no DRF imports.
- `_resolve_direct_send_flag` lives on `AssignAgentUseCase` (a Use
  Case) and consumes `IntegrationsService.get_channel_app` (a
  Service that already returns `None` on failure) — boundary
  preserved.

### II. DRF Composition for AuthN/AuthZ — PASS

No new endpoints. `AssignAgentView`'s
`permission_classes = [IsAuthenticated, HasProjectPermission, IsAgentOficialOrFromProjet]`
is unchanged. The use case never touches `request` or permissions.

### III. Test Coverage Parity & Isolated Tests (NON-NEGOTIABLE) — PASS (with planned tests)

Every new code branch will be exercised by tests in the same PR
(`tasks.md` will enumerate them). Notable points:

- The new `MetaClient.fetch_library_template_by_name_and_language`
  is covered by `unittest.mock.patch` on `make_request` (no live
  Meta call).
- `IntegrationsService.get_channel_app` is mocked at the service
  boundary in the assignment-use-case tests.
- New use-case tests use `MagicMock(spec=...)` for both
  `MetaService` and `IntegrationsService`.
- The `PAUSED`/`FLAGGED` dispatch gate is covered by direct
  database fixtures (no cache, no Redis, no broker).
- Snapshot test for the legacy payload pins Story 4's byte-for-byte
  guarantee.
- No `# pragma: no cover` is required for new code (no live external
  provider involved, no `__main__` block introduced).

### IV. Self-Documenting Code — PASS

- New methods carry intent in their names
  (`_resolve_direct_send_flag`, `fetch_library_template_by_name_and_language`,
  `build_direct_send_message`, `_substitute_template_variables`,
  `is_valid_direct_send_template_name`).
- Docstrings are reserved for non-obvious *why* (e.g. why the
  `pt_BR` fallback is per-template, why the helper is shared with
  push-time validation).
- Logging follows the project's existing pattern: f-strings,
  identifiers (`agent={...}`, `template={...}`, `app_uuid={...}`),
  level semantics matching the spec (warning on fallback, info on
  milestone, error on failure with context, audit-log warning on
  skip).
- Single Level of Abstraction Principle is preserved by extracting
  `_substitute_template_variables` and the `TemplateInfo` adapter
  into helpers instead of inlining them in the dispatch builder.

### V. Conventional Commits & Structured PRs — PASS

The plan ships under one PR with a `feat:` prefix:

- Branch: `002-direct-send-broadcasts` (spec-kit numeric-prefix
  convention auto-generated by the `before_specify` git hook;
  deviation from Principle V's `<type>/<kebab>` form is documented
  and justified in §Complexity Tracking below).
- PR title (≤72 chars): `feat: add WhatsApp Direct Send dispatch path for OrderStatus`.
- PR description follows the `## What` / `## Why` template.
- No new column is added to `IntegratedAgent` — the Direct Send
  flag is stored as an optional key inside the existing
  `IntegratedAgent.config` JSON (data-model.md §1 Decision). The
  model's existing legacy UUID PK is unaffected, no PK migration
  is implied, and Principle V's "no schema churn beyond what's
  necessary" rule is satisfied. The single migration that ships
  with the feature is the additive `Version.STATUS_CHOICES`
  extension (templates app), which does not change any model PK.

### Constitution Check verdict

**No violations.** The plan does not require entries in
`Complexity Tracking`. The Constitution Check was re-evaluated
after Phase 1 design (data-model, contracts, quickstart) and the
verdict stands.

## Project Structure

### Documentation (this feature)

```text
specs/002-direct-send-broadcasts/
├── plan.md                              # This file (/speckit-plan command output)
├── research.md                          # Phase 0 — design decisions resolved
├── data-model.md                        # Phase 1 — persisted state changes
├── contracts/
│   ├── messaging-gateway-payload.md     # Flows broadcast payload (legacy + Direct Send)
│   ├── meta-library-catalog.md          # Meta library-catalog GET semantics
│   └── integrations-channel-app.md      # Integrations channel-app GET semantics
├── quickstart.md                        # End-to-end happy-path validation script
├── checklists/                          # Existing (created by /speckit-checklist runs, if any)
├── spec.md                              # Feature specification (/speckit-specify output)
└── tasks.md                             # Phase 2 output (NOT created by /speckit-plan)
```

### Source Code (repository root)

The feature touches only existing apps. No new Django app, no new
URL, no new view. Files marked **NEW** are added; **MOD** is
modified in place; everything else is read-only context.

```text
retail/
├── agents/
│   ├── domains/
│   │   ├── agent_integration/
│   │   │   ├── exceptions.py                               # MOD — add DirectSendTemplateUnavailableError + DirectSendUnsupportedComponentError (T007)
│   │   │   ├── serializers.py                              # MOD — expose direct_send (read-only, computed from config["direct_send"])
│   │   │   └── usecases/
│   │   │       └── assign.py                               # MOD — branch on Direct Send: read channel flag,
│   │   │                                                   #       write agent.config["direct_send"], fetch from
│   │   │                                                   #       Meta library catalog, persist Template+Version
│   │   │                                                   #       with status=APPROVED, raise
│   │   │                                                   #       DirectSendTemplateUnavailableError on FR-003d
│   │   ├── agent_management/
│   │   │   └── usecases/
│   │   │       └── validate_templates.py                   # MOD — collapse _get_template_info into shared helper
│   │   └── agent_webhook/
│   │       ├── services/
│   │       │   ├── broadcast.py                            # MOD — add build_direct_send_message + audit-log
│   │       │   │                                           #       entry for PAUSED/FLAGGED in get_current_template
│   │       │   ├── direct_send_constants.py                # NEW — Direct Send length-limit constants (T007a)
│   │       │   └── direct_send_payload_builder.py          # NEW — small helpers (variable substitution, naming
│   │       │                                                #       rule check, header/footer/buttons builders)
│   │       └── usecases/
│   │           └── webhook.py                              # MOD (minimal, only if route selection moves out of
│   │                                                       #       Broadcast.build_message)
│   └── (no new migration — the Direct Send flag lives inside the existing IntegratedAgent.config JSON; data-model.md §1 Decision)
├── clients/
│   └── meta/
│       └── client.py                                       # MOD — add fetch_library_template_by_name_and_language
├── interfaces/
│   ├── clients/meta/client.py                              # MOD — extend Protocol
│   └── services/meta.py                                    # MOD — extend Protocol
├── services/
│   └── meta/
│       └── service.py                                      # MOD — add fetch_library_template_by_name_and_language
├── templates/
│   ├── models.py                                           # MOD — extend Version.STATUS_CHOICES
│   ├── migrations/
│   │   └── 0017_alter_version_status_paused_flagged.py     # NEW — AlterField with PAUSED/FLAGGED
│   └── usecases/
│       ├── _meta_library_template_fetch.py                 # NEW — shared adapter (Decision 9; further tightened by Phase 8 / T120 — FR-003e / FR-003f / 2026-05-22 Q3)
│       └── update_template.py                              # MOD — extend UpdateTemplateData.status Literal
└── api/
    └── integrated_agent/
        └── usecases/
            └── send_test_template.py                       # MOD — surface PAUSED/FLAGGED reason in error message

retail/  # tests
├── agents/
│   ├── tests/
│   │   ├── usecases/
│   │   │   ├── test_assign_agent.py                        # MOD — add Direct Send branches
│   │   │   └── test_assign_direct_send.py                  # NEW — focused tests for the Direct Send branch
│   │   ├── services/
│   │   │   ├── test_broadcast.py                           # MOD — get_current_template PAUSED/FLAGGED audit log
│   │   │   ├── test_broadcast_direct_send.py               # NEW — Direct Send payload + variable substitution + length limits (T010–T011d)
│   │   │   ├── test_broadcast_direct_send_persistence.py   # NEW — Direct Send BroadcastMessage persistence parity (T011e, FR-016 / SC-005)
│   │   │   ├── test_broadcast_legacy_datalake.py           # NEW — legacy datalake event snapshot (T035a, FR-020 / SC-008)
│   │   │   ├── test_broadcast_legacy_observability.py      # NEW — legacy Sentry / APM tag snapshot (T035b, FR-027 / SC-008)
│   │   │   ├── test_broadcast_legacy_payload.py            # NEW — legacy payload byte-shape snapshot tests (Story 4)
│   │   │   └── test_direct_send_payload_builder.py         # NEW — pure unit tests for helpers
│   │   └── views/
│   │       └── test_integrated_agent_viewset.py            # MOD — direct_send appears in serializer output
├── api/
│   └── integrated_agent/
│       └── tests/
│           └── test_send_test_template.py                  # MOD — surface PAUSED/FLAGGED reason in error message (T030, T032)
├── templates/
│   └── tests/
│       └── usecases/
│           ├── test_meta_library_template_fetch.py         # NEW — exact-match + adapter shape tests (extended by Phase 8 / T107–T111)
│           └── test_update_template.py                     # MOD — FR-026 PAUSED/FLAGGED behavioural test (T030a)
├── services/
│   └── meta/
│       └── tests/test_meta_service.py                      # MOD — add fetch_library_template_by_name_and_language
└── clients/
    └── meta/
        └── tests/test_meta_client.py                       # MOD — add fetch_library_template_by_name_and_language
```

**Structure Decision**: this is the existing Django + DRF backend
under `retail/`, organized per-domain (`agents/domains/<domain>/`).
The feature adds no new top-level package; every change lands in an
existing module to keep discovery aligned with how the team finds
code today (e.g. broadcast logic in
`agents/domains/agent_webhook/services/broadcast.py`, assignment
logic in `agents/domains/agent_integration/usecases/assign.py`).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations. The eight items below are recorded for
auditability: a deliberate test-coverage gap (FR-022 / FR-023 /
FR-024 untestable by design), a workflow-driven branch-name
deviation from Constitution Principle V, the four-checklist
resolution-map gate, the FR-043 explicit-cross-validation
deferral, the FR-041 unchanged-existing-behavior coverage
acceptance, the FR-038 Celery one-shot "satisfied by absence"
coverage acceptance, the FR-034 / FR-035 / FR-036 / FR-037
existing-behavior-restated coverage acceptance (no new tests in
this PR; covered by pre-existing tests + SC-009 SQL parity checks
in `quickstart.md §10`), and the SC-009 (b)–(e) structural-guarantee
coverage acceptance (no new tests in this PR; guaranteed by
pre-existing FR-032 / FR-034 constraints + the same operational
SQL parity checks). None of these is a hard MUST violation; they
are recorded here so reviewers see the full set of
justified-and-documented trade-offs in one read.

| Issue | Why it is acceptable | Simpler alternative rejected because |
|-------|----------------------|--------------------------------------|
| FR-022 (no new required field on inbound payloads), FR-023 (template-status webhook untouched), FR-024 (no new env var) are not exercised by an automated test. | All three are "thou shalt not" requirements: their compliance is structural — there is no positive code path to exercise; the requirement is satisfied by the *absence* of changes. The reviewer + the backward-compatibility checklist (`checklists/backward-compatibility.md` CHK013–CHK022, CHK027–CHK029) are the agreed-upon enforcement gate. | A meta-test that diffs every serializer's `required` set, the template-status webhook handler signature, and `settings.py` keys against a pinned baseline would have a high false-positive rate during normal feature evolution and would force every unrelated PR through this analysis. The cost outweighs the benefit. |
| FR-038 (Celery one-shot — `task.retry(...)` NOT used, `acks_late=False` early-ack, no DLX in v1; re-delivery absorbed by FR-035 / FR-036 / FR-028) is not exercised by an automated test. | Same "thou shalt not" class as the FR-022 / FR-023 / FR-024 row above: compliance is structural — the requirement is satisfied by the *absence* of changes to `retail/celery.py` (no `task_acks_late=True` override, no `task_default_retry_delay` change, no broker DLX configuration added) and by the *absence* of `self.retry(...)` / `bind=True, retry_kwargs={...}` decorators on the three OrderStatus-pipeline tasks (`task_order_status_update`, `task_mark_broadcast_converted`, `handle_purchase_event_task`). The reviewer + the idempotency checklist (`checklists/idempotency.md` CHK014) + the PR-body backward-compatibility gate (`tasks.md` T039) are the agreed-upon enforcement gate. The PR diff for `retail/celery.py` MUST be empty for retry-related keys, and the PR diff for the three task functions MUST NOT introduce `bind=True` or `retry`-related kwargs. | A snapshot test that captures `celery_app.conf.task_acks_late`, `celery_app.conf.task_default_retry_delay`, and every Celery task decorator's `retry_kwargs` against a pinned baseline would have the same high false-positive rate as the FR-022 meta-test (every unrelated Celery configuration tweak would have to pass through this gate). The cost outweighs the benefit; structural absence + the existing idempotency contracts (FR-035 / FR-036 / FR-028 absorb every legitimate re-delivery source) make the runtime guarantee observable without a dedicated test. |
| Branch name is `002-direct-send-broadcasts` (spec-kit numeric-prefix convention) rather than the Constitution Principle V form `feature/<kebab-description>`. | The numeric-prefix form is created automatically by the spec-kit `before_specify` git hook (`.specify/extensions.yml`) and is the convention documented in `docs/SPEC_KIT.md` for every spec-driven feature in this repo. Reusing the auto-generated branch keeps the spec-kit artifacts, the git history, and the PR metadata co-located under a single identifier (`002-…`). | Renaming the branch to `feature/direct-send-broadcasts` mid-feature would break the spec-kit tooling's branch ↔ `specs/<id>/` association and force a manual rename of every cross-reference in `spec.md` / `plan.md` / `tasks.md`. A constitution amendment to formally codify the spec-kit exemption is a separate, repo-wide change that does not belong in this feature's PR. |
| All four checklists (`checklists/requirements.md`, `checklists/backward-compatibility.md`, `checklists/idempotency.md`, `checklists/tenant-isolation.md`) are now resolved against the spec / plan / research / data-model / contracts (resolution maps appended to each checklist). | The merge gate for this feature spans the union of those resolution surfaces; each checklist carries a Resolution Map at the bottom that traces every CHK item to the FR / Decision / Constraint / Contract clause that resolved it. | Leaving any of the checklists with open items would invite reviewer ambiguity at merge time. The Resolution Maps make the gate evaluable in a single read. |
| FR-043 (assignment surface MUST cross-validate the `app_uuid` query param against the `Project-Uuid` header and DENY with HTTP 403 on mismatch) is satisfied **transitively** at v1 — through DRF's `HasProjectPermission` on `AssignAgentView`, Integrations Engine's authorization on `GET /api/v1/apptypes/wpp-cloud/apps/{app_uuid}/`, and `IntegrationsService.get_channel_app(...)`'s fail-closed `None` return on any HTTP error — rather than by an explicit Retail-side equality check (`app["config"]["project_uuid"] == request.headers["Project-Uuid"]`). The explicit cross-validation is **deferred** to a separate `feat/tenant-isolation-cross-validation` PR. | The transitive guarantee already closes the cross-tenant attack surface described in `spec.md` Edge Cases ("Operator with permission on project A passes project B's `app_uuid` …") for v1: an operator authorized for project A who supplies project B's `app_uuid` is rejected at one of the three layers before any persistence happens. The explicit Retail-side check is a defense-in-depth follow-up that protects against a regression in any of the three upstream layers, not a v1 attack-surface gap. The trust boundary on Integrations Engine is documented as an Assumption in `spec.md`, in `contracts/integrations-channel-app.md` §9, and as a known dependency in `checklists/tenant-isolation.md` CHK044 (the explicit "Integrations Engine enforces channel-app-to-project ownership" precondition); the checklist's CHK022 / CHK023 / CHK024 / CHK025 capture the cross-validation requirement items that this row defers. | Implementing the explicit cross-validation in this PR would require an additional `IntegrationsService.get_channel_app(...)` call inside `AssignAgentView.post` (or a new `TenantBindingPermission` class), plus a new audit-log shape (`[DirectSend] channel_project_mismatch: ...`), plus the corresponding test fixture combinations (matching project, mismatched project, channel-app lookup failure). The work is well-scoped on its own and benefits from being reviewed independently of the Direct Send dispatch path; bundling it would expand this PR's surface without changing the v1 attack surface. |
| FR-041 (Inbound EDA event consumers MUST resolve the target tenant deterministically via `Project.uuid` payload reference, `BroadcastMessage.broadcast_id` lookup, `BroadcastMessage.external_message_id` lookup, or `Project.vtex_account` lookup with the `MultipleObjectsReturned → None` SECURITY BOUNDARY) is **not exercised by a NEW automated test introduced by this feature**. | The feature does not modify the inbound EDA consumers (`BroadcastSendConsumer` on `retail.template-send`, `BroadcastStatusConsumer` on `retail.template-status`, the order-status webhook entry point at `retail/agents/domains/agent_webhook/usecases/order_status.py:213`); their tenant-resolution mechanisms are existing behaviors **restated as requirements** by FR-041, not new code paths added by this PR. The pre-existing tests on these consumers (notably the order-status webhook tests in `retail/agents/tests/usecases/test_order_status_update.py` and the broadcast consumer tests in `retail/broadcasts/tests/`) already cover the four resolution mechanisms. The Direct Send cohort is additionally covered transitively by T035c (cross-project regression: `BroadcastMessage.project_id == BroadcastMessage.integrated_agent.project_id`), which exercises the `broadcast_id`-keyed resolution path end-to-end against two-project fixtures. | A meta-test that diffs every inbound consumer's tenant-resolution mechanism against a pinned baseline would have a high false-positive rate during normal feature evolution and would force every unrelated PR through the diff (same cost calculus as the FR-022/FR-023/FR-024 row above). Adding a duplicate behavioral test for the Direct Send cohort would re-cover the FR-040 / SC-010 surface that T035c already pins, doubling test runtime without raising the merge gate. The pre-existing tests + T035c are the agreed enforcement gate. |
| FR-034 (`IntegratedAgent.broadcasts_delivered` atomic-but-not-idempotent counter; incremented exactly once per FIRST DELIVERED transition via the `is_first_delivery` predicate), FR-035 (inbound RabbitMQ status-update consumer retry-safety via `select_for_update` + `broadcast_id`/`external_message_id` lookup + lifecycle-rank guard), FR-036 (`MarkBroadcastConvertedUseCase` idempotency via `BroadcastConversion.objects.get_or_create((project, order_id))`), and FR-037 (`RecordBroadcastSentUseCase` called-at-most-once invariant preserved by the `Broadcast.send_message` / `_record_failed_dispatch` exception-swallowing paths) are **not exercised by NEW automated tests introduced by this feature**. | Same cohort treatment as the FR-041 row above: the feature does not modify any of these surfaces; the requirements **restate existing behavior** so the merge gate can detect a future regression that drops the invariant. Pre-existing tests cover each contract — counter parity in `retail/broadcasts/tests/test_models.py` and the broadcast consumer tests; `select_for_update` + lifecycle-rank in the broadcast consumer tests; `get_or_create`-keyed conversion in the conversion use-case tests; `RecordBroadcastSentUseCase` called-at-most-once via the `Broadcast.send_message` / `_record_failed_dispatch` tests. The Direct Send cohort is additionally covered transitively by T011e (BroadcastMessage persistence parity on Direct Send happy path + refusal paths). For operational parity, `quickstart.md §10.5` provides the post-deploy SQL parity check for the FR-034 counter (`IntegratedAgent.broadcasts_delivered == COUNT(BroadcastMessage WHERE status IN (DELIVERED, READ))` after a quiescent period). | A meta-test that diffs every status-transition / counter / `get_or_create` site against a pinned baseline would have a high false-positive rate during normal feature evolution and would force every unrelated PR through the diff (same cost calculus as the FR-022/FR-023/FR-024 and FR-041 rows above). Adding duplicate behavioral tests for the Direct Send cohort would re-cover the FR-016 / SC-005 surface that T011e already pins, doubling test runtime without raising the merge gate. The pre-existing tests + T011e + the `quickstart.md §10.5` SQL parity check are the agreed enforcement gate. |
| SC-009 (b) (`COUNT(DISTINCT broadcast_id WHERE broadcast_id IS NOT NULL) == COUNT(BroadcastMessage WHERE broadcast_id IS NOT NULL)`), SC-009 (c) (same equality for `external_message_id`), SC-009 (d) (`COUNT(DISTINCT (project_id, order_id)) == COUNT(BroadcastConversion)`), and SC-009 (e) (`IntegratedAgent.broadcasts_delivered` equals current `DELIVERED`/`READ` count after a quiescent period) are **not exercised by NEW automated tests introduced by this feature**. SC-009 (a) (at-most-one-broadcast-per-canonical-tuple within the dedup window) IS covered by T014a (Direct Send cohort) + the pre-existing legacy dedup tests in `retail/agents/tests/usecases/test_order_status_update.py`. | (b) and (c) are **structurally guaranteed** by the conditional unique constraints `broadcasts_broadcast_id_unique` / `broadcasts_external_message_id_unique` already shipped on `BroadcastMessage` (restated as FR-032) — a violation would raise `IntegrityError` at insert time, making the equality a runtime invariant Django enforces at the DB level. (d) is **structurally guaranteed** by the `broadcast_conversions_project_order_unique` constraint on `BroadcastConversion` (restated as FR-033) combined with `MarkBroadcastConvertedUseCase`'s `get_or_create` semantics (FR-036). (e) is **structurally guaranteed** by the `F("broadcasts_delivered") + 1` atomic increment gated by `_apply_status_transition`'s `is_first_delivery` predicate (FR-034) plus FR-035's lifecycle-rank guard that rejects backwards transitions — every row currently in `READ` was counted exactly once at its prior `DELIVERED` transition. All four invariants are observable via the SQL parity checks in `quickstart.md §10.2 / §10.3 / §10.4 / §10.5` (non-destructive checks that can be scheduled as a periodic data-quality job; any non-zero result is a candidate defect). | A behavioral test that drives N broadcasts end-to-end and asserts each SQL invariant would re-cover surfaces already pinned by FR-032/FR-033/FR-034 unit tests and the constraints themselves, doubling test runtime without raising the merge gate. The pre-existing constraints + pre-existing unit tests + the `quickstart.md §10` SQL parity checks are the agreed enforcement gate. The constraints themselves cannot be silently dropped because FR-032 / FR-033 restate them as requirements; a future migration that drops either fails code review by virtue of these requirements. |
