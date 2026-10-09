# Implementation Plan: Shopping Assistant Opt-in — retail-setup orchestration

**Branch**: `005-shopper-phone-optin` | **Date**: 2026-10-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-shopper-phone-optin/spec.md`, inheriting product spec `001-new-client-phone-optin-v1.5` (`52d927b`) and its architecture document at the same tag, BD-001 – BD-027, no divergences.

**Artifacts**: [research.md](./research.md) · [data-model.md](./data-model.md) · [contracts/](./contracts/) · [quickstart.md](./quickstart.md)

## Summary

retail-setup becomes the Opt-in orchestrator: it stores per-project Opt-in settings (including the Shopping Assistant flag written by agentic-cx, the coupon and its sender), the authenticated eligibility record (project × normalized email), one record per accepted submit, and an Opt-in flag on abandoned carts. It makes every Flows call, owns the coupon-send automation, and consumes Flows' `channel.deleted` event.

Technical approach (details and alternatives in research.md):

- **New app `retail.opt_in`** with three models (`OptInSettings`, `OptInEligibility`, `OptInSubmit`) and one new column + partial unique index on `Cart` (D-2).
- **Merchant settings** (`GET/PUT /api/v3/opt-in/settings/`) enforce the gates server-side, ensure the Flows group **Opt-in** (and the `identifier` contact field) on enable, and never fail because of coupon-send readiness (D-12, D-13, D-21).
- **Coupon-send** is an official active agent. It shares only the **structure** of the other official active agents (order-status, abandoned-cart, back-in-stock): same models, Lambda invoke via `AgentWebhookUseCase.execute_from_task`, broadcast dispatch and execution logs. Its business rules are its own and are not shared with any other agent. Like every official active agent, it may have custom agents of its own, linked to it (and only to it) through `IntegratedAgent.parent_agent_uuid`. Custom agents keep today's mechanism (official first, else the custom child; always one agent). Children are matched by the exact parent UUID, so each official agent resolves only its own children; the order-status lookup was fixed accordingly in a separate PR already on `main` ([#590](https://github.com/weni-ai/retail-setup/pull/590), F15). First creation reuses `AssignAgentUseCase`; reactivation flips the same `IntegratedAgent` (assign would create a second one); deactivation reuses `UnassignAgentUseCase`; generic assign/unassign stay as today. A single idempotent reconciler runs the readiness check (Integrations read of the sender's current version), repairs only missing or misaligned versions from local metadata, and activates (D-3, D-5).
- **Liveness** = coupon on ∧ sender set ∧ latest version for the sender's app is `APPROVED` ∧ status confirmed within 15 minutes. Status comes from the existing per-version webhook, a new Integrations read, and a 5-minute refresh; the storefront payload is cached for 60 s and invalidated on every settings/SA/disconnect change (D-4).
- **Submit**: accept and record (`completed_at` first), one synchronous Flows attempt bounded to 2 s and skipped when a circuit breaker is open, then background resolution on a dedicated queue with bounded exponential backoff, per-identity lock, compare-and-set transitions and recoverable exhaustion. "Already in Opt-in" is read from the lookup's groups (D-6).
- **Jobs 2 and 3** run on a second dedicated queue. Coupon sends invoke the effective coupon-send agent (Lambda → regular broadcast path) bound to the sender stored at send time, and are retried only when they certainly did not reach Flows. Enrollment reads the order form and registers through the notification processing (D-14, D-15).
- **Cart idempotency** per `order_form_id` × project applies only to projects with Opt-in on, so every other project keeps today's exact behavior; `opt_in` is optional on the notification (D-8).
- **`channel.deleted`** consumed from `flows-channel-events.topic` on `channel.deleted.wac`, matched by project + Flows channel UUID (D-1, D-22).
- **PII-safe logging** on every reused path, opaque Sentry user id, feature-scoped correlation id (D-18, D-19).

## Technical Context

**Language/Version**: Python 3.10 (`pyproject.toml`).

**Primary Dependencies**: Django 5, DRF 3.15, Celery + Redis (`django-redis`), `weni-eda` (consumer), `weni-commons` auth (`WeniAuthMixin`, `IsWeniAuthenticated`, `CanCommunicateInternally`), `phonenumbers` (already present), `requests` via `RequestClient`. No new third-party dependency.

**Storage**: PostgreSQL (single primary, no replica router — reads after writes are consistent, FR-014). Three new tables; `vtex_cart` gets `opt_in` (metadata-only add) and a partial unique index created `CONCURRENTLY`. Redis for the storefront cache, locks and the circuit breaker only (never a system of record).

**Testing**: `django.test.TestCase`, `APIClient`, `unittest.mock`; LocMemCache per test class; Flows/Integrations/VTEX mocked at the client boundary; broker untouched (consumer `consume()` is `# pragma: no cover`, parser and use case fully tested). Flow tests per user story (see Constitution IX below).

**Target Platform**: Linux containers (`docker/entrypoint.sh`): gunicorn web, Celery workers `opt-in-contact` and `opt-in-followup` (new deployments), Celery beat, `edaconsume`.

**Project Type**: Web service (Django + DRF backend).

**Performance Goals**: SC-011 — p99 < 1 s for storefront settings and eligibility reads at ≥ 10,000 transactions/min and above. SC-012 — 0 valid submits rejected under load.

**Constraints**: Every outbound call has a named timeout (FR-039); submit request budget for Flows ≤ `OPT_IN_SUBMIT_SYNC_BUDGET_SECONDS`; coupon status changes visible in ≤ 15 min (FR-005d, enforced by a system check); no PII in logs, Sentry, Celery args or Redis key names (FR-038); backward-compatible abandoned-cart notification (FR-040).

**Scale/Scope**: ~25 new production modules in `retail/opt_in/`, targeted changes in existing files (listed under Project Structure), 2 migrations (`opt_in/0001_initial` with 3 tables, `vtex/0016_cart_opt_in`), 2 new Celery queues, 1 new EDA queue, 3 new beat schedules (status refresh, stale-submit sweeper, submit retention), 1 management command, 1 new official agent (Lambda, cross-repo).

No `NEEDS CLARIFICATION` remains: every unknown was resolved in research.md (D-1 … D-24), using the real producer/consumer code of Flows and the integrations engine.

## Peak load *(constitution V)*

Declared in the spec: ≥ 10,000 transactions/min (≈ 167/s) as a floor, spikes above it expected.

| Path | Work per request | Design for spikes |
|---|---|---|
| Storefront settings | JWT verify + 1 Redis GET (miss: cached project lookup + 2 indexed queries) | Cache per VTEX account, TTL 60 s; cache errors fall back to DB without failing |
| Eligibility read | JWT verify + cached project lookup + 1 unique-index lookup on the primary | No cache by contract; single-index access path |
| Skip / promote | 1 transaction on one row | `select_for_update` on one row; promotion's identifier fill is async |
| Submit | 1 insert (+1 upsert when logged in) + ≤ 2 s Flows attempt | Breaker skips the attempt when Flows degrades → request cost ≈ one transaction; nothing rejected (SC-012); kill switch `OPT_IN_SUBMIT_SYNC_ATTEMPT_ENABLED` for planned peaks |
| Flagged cart notification | existing path + order-form lock | Lock and lookup on the existing `(order_form_id, project)` index |
| Background | 2–3 Flows calls per submit; coupon send; order-form read | Two dedicated queues scaled independently (FR-041); bounded retries with jitter; per-identity and per-project locks in Redis |
| Flows throttle | 2500 `contacts.json` calls/hour **per org**, shared with other retail callers (D-25) | Per-project token bucket below the limit; no token → submit stays pending without consuming attempts; `429` honors `Retry-After` |

Capacity note: with sync workers, a submit that waits the full 2 s budget holds a worker; at 17 submits/s that is ~34 worker-seconds/s, which the breaker removes as soon as Flows starts failing. Opening a new DB connection per request (`CONN_MAX_AGE` unset) is the dominant fixed cost of the eligibility read; tuning it is a platform follow-up, not part of this change (constitution XI).

## Constitution Check

*Gate evaluated before Phase 0 and re-evaluated after Phase 1 design. Reference: `.specify/memory/constitution.md` v2.0.0.*

### I. Layered Clean Architecture (NON-NEGOTIABLE) — PASS

- Views (`retail/opt_in/api/views.py`) only validate with serializers (`retail/opt_in/api/serializers.py`), build frozen DTOs, compose services, call one use case and map domain exceptions to the stable error shape. No ORM, no clients.
- Use cases (`retail/opt_in/usecases/`) hold every rule, ORM query and orchestration; none imports `rest_framework`. Existing use cases that raise DRF exceptions (`AssignAgentUseCase`, `UnassignAgentUseCase`) are wrapped, and their exceptions are translated at the wrapper boundary.
- Services: `FlowsContactService` (typed `FlowsTransientError` / `FlowsRejectedError`, never raw `CustomAPIException`), `WhatsAppChannelsService`, `CouponTemplateStatusService`. Clients: `FlowsClient` (+ `update_contact_fields`, fields endpoints), `IntegrationsClient` (+ `list_whatsapp_cloud_channels`, `get_template_by_name`), each method added to its `Protocol` in `retail/interfaces/clients/...`. DI via `Optional[...] = None` everywhere.
- The consumer and Celery tasks are entry points like views: they parse, build DTOs and call use cases.

### II. Never Trust the Client — PASS

- Every HTTP input goes through a serializer; phone validation by `phonenumbers` (D-11); `skip_until` from the browser is clamped (D-16); browser-supplied names are never stored (FR-016); the email comes only from the signed JWT claim (FR-035).
- AuthN/AuthZ exclusively in `permission_classes`: merchant `[IsWeniAuthenticated, HasWeniProjectPermission]`; SA write `[IsWeniAuthenticated, CanCommunicateInternally]`; storefront `[IsWeniAuthenticated, IsStorefrontRetailToken]` (new `BasePermission`, rejects Keycloak callers whose tenant would come from request locations). No permission logic in bodies or use cases.
- EDA payload validated explicitly (contracts/flows-channel-deleted-event.md). The consumer re-checks `channel_type` even though the binding filters it (last bullet of II).
- Generic assign/unassign of agents stay as today; the reconciler converges coupon-send to the single agent the role lookup returns, and reactivates it while the coupon is on (FR-005).
- Children are resolved by exact parent UUID (`ORDER_STATUS_AGENT_UUID` for order-status, `OPT_IN_COUPON_AGENT_UUID` for coupon-send), so one official agent's children are never resolved as another's (research F15).

### III. Fail Gracefully and Predictably — PASS (explicit check)

- **Timeouts**: every Flows, Integrations and VTEX call made by Opt-in uses a named setting (`OPT_IN_*_TIMEOUT_SECONDS`, `OPT_IN_SUBMIT_SYNC_BUDGET_SECONDS`) passed through per-instance client options; `RequestClient`'s inline `60` becomes `DEFAULT_REQUEST_TIMEOUT_SECONDS` (D-7).
- **Stable errors**: `{"error_code", "detail", "fields"}` for every Opt-in endpoint; codes enumerated in the OpenAPI contract. Upstream bodies never leak into responses.
- **Shopper never sees a Flows failure** (FR-027): valid submit → 200/202. **Merchant never sees a readiness failure** (FR-005b): reconciler is async.
- **Fail-safe utilities**: cache invalidation, breaker counters and log enrichment swallow and log their own errors.
- Cache unavailability degrades the storefront read to the database instead of failing.

### IV. Bounded Retry Over REST — PASS with one recorded exception (explicit check)

| Operation | Retried on | Bound / backoff | Idempotency | Exhaustion |
|---|---|---|---|---|
| Job 1 (Flows lookup + create/add) | conn, timeout, 5xx, 429 (`Retry-After` honored) | `OPT_IN_SUBMIT_MAX_ATTEMPTS`, exp. backoff base/cap settings, jitter; waiting for the per-project Flows budget does not consume attempts (D-25) | fresh lookup each attempt + per-identity lock + Flows URN uniqueness + CAS | `exhausted` row, error log + Sentry, `opt_in_redispatch_submits`; stale-pending sweeper for lost tasks (never touches `exhausted`) |
| Job 3 (order form read + cart register) | conn, timeout, 5xx, 429 | `OPT_IN_FOLLOWUP_*` | order-form idempotency (D-8) + CAS | `failed`, logged, re-dispatchable |
| Identifier fill | same | `OPT_IN_FOLLOWUP_*` | fresh lookup, write only when empty | `failed`, logged, re-dispatchable |
| Reconciler (Integrations read / repair) | same | `OPT_IN_FOLLOWUP_*` | converges to DB state under per-project lock | status unconfirmed → not live; periodic refresh re-runs it |
| Coupon send (agent Lambda → Flows broadcast) | Lambda invoke failure before broadcast; Flows conn error before send, 429 | `OPT_IN_FOLLOWUP_*` | CAS claim | **ambiguous failures not retried** → `failed_ambiguous`, re-dispatchable by operator — see Complexity Tracking; Lambda "no send" → `skipped_not_dispatched` |
| `channel.deleted` processing | broker redelivery on infra failure | quorum queue delivery limit + DLX | idempotent match | dead-letter queue |

4xx that reflect a defect in the request are never retried.

### V. Scalability and Peak Load — PASS (explicit check)

Peak declared in the spec and designed for above. Web, workers and consumer are stateless; locks, dedup windows and the breaker live in Redis via `django.core.cache` (testable with LocMemCache); durable state in Postgres. Two dedicated queues isolate Opt-in from other jobs (FR-041).

### VI. Security and Secrets — PASS

No new secrets (module JWT and OIDC already configured). SA-state write limited to internal callers (least privilege). Opt-in client instances redact request/response payloads **and headers** from logs and Sentry, so the `Authorization` leak noted in the constitution TODO does not happen on these calls. `opaque_user_id` uses an HMAC with the existing `SECRET_KEY`.

### VII. Observability and Diagnosable Errors — PASS (explicit check)

- Structured f-string logs with `key=value` (`project_uuid`, `vtex_account`, `submit_uuid`, `correlation_id`, `outcome`, `attempt`); levels per constitution.
- No names, emails or phones in logs, Sentry, Celery args or Redis keys (D-18); the reused cart/broadcast log lines are fixed as part of this change; a test helper asserts it in every flow test (SC-010).
- Correlation id propagated HTTP → DB row → Celery kwargs → logs/Sentry; EDA uses `event_id` (D-19). Project-wide correlation remains a constitution TODO outside this scope.
- Sentry via `sentry_error_scope` with `project_uuid`, `vtex_account`, opaque `user_id`, `correlation_id`; fingerprints `["opt-in", <error type>, vtex_account]`.

### VIII. Versioned Contracts — PASS

New endpoints under `/api/v3/opt-in/`, contract SemVer `1.0.0` (contracts/opt-in-api.openapi.yaml). Abandoned-cart notification gains an optional field with default `false`; response unchanged. Consumed event read tolerantly. Outbound contracts documented.

### IX. Tests Exercise Flows & Coverage Parity (NON-NEGOTIABLE) — PASS (planned)

Flow tests (`APIClient`/entry point → use case → persisted state / client-boundary call), each with success and failure paths:

| Flow | Success | Failure paths covered |
|---|---|---|
| Merchant save/read | US1 scenarios 1–14 | SA not enabled / never recorded, no WhatsApp, missing fields, sender not connected, group ensure fails (nothing stored), Integrations list down (503), readiness Integrations down (save still 200) |
| SA state write | enable/disable/no-op | non-internal caller 403, unknown project 404 |
| Reconciler | create official, reactivate FK agent, rebind, adopt the active agent the role lookup returns (official or child), official unassigned in Automations → reactivated while coupon on, repair missing, repair misaligned, no repair for pending/rejected | Integrations timeout → retry → exhaustion → not live; lock busy; multiple children → error log, no activation |
| Agent resolution | official first, else child; single agent | multiple children of the same parent; order-status ignores children of other official agents (`test_order_status_parent_agent_scope.py`) |
| Status freshness | webhook APPROVED → live within TTL; refresh confirms | unreadable → not live after window; system check E001 |
| Storefront settings | live / not live / unavailable | cache down → DB fallback; unknown account 404 |
| Eligibility / skip / promote | US3 scenarios 1–11 | anonymous 400, promotion with unknown phone (no name/phone), past `skip_until` no-op, existing row not weakened |
| Submit + job 1 | created, added, already-in-Opt-in, logged-in and anonymous | invalid fields (no write, no Flows call), Flows timeout → pending → retry resolves, 4xx → exhausted, max attempts → exhausted, concurrent submits → one contact, create race → re-lookup, breaker open |
| Job 2 | live send through the agent pipeline from current sender (official and custom child) | not live → skipped (no retro send), agent inactive, no designated template, Lambda returns no template → `skipped_not_dispatched`, Lambda invoke error retried, 429 retried, read timeout → `failed_ambiguous` not retried |
| Job 3 | enroll flagged | AC disabled, no order form, empty cart, order form unreadable, retry after 5xx |
| Cart notification | flagged create/update/keep | Opt-in off drops flag, AC off unchanged, no `opt_in` identical to today, partial-index race |
| `channel.deleted` | sender deleted → coupon off | non-sender, duplicate, unknown project, malformed, non-WhatsApp, DB failure → nack |
| Identifier fill | created + empty → filled | non-empty, added/already contacts untouched |

Isolation: every test class uses `@override_settings(CACHES=LocMemCache, unique LOCATION)`; Flows/Integrations/VTEX/broadcast mocked at the client; Celery tasks called directly or with `CELERY_TASK_ALWAYS_EAGER`; no broker. `# pragma: no cover` only on `ChannelDeletedConsumer.consume` (broker-only) with justification. Coverage parity checked with `contrib/compare_coverage.py`.

### X. Explicit Over Clever — PASS

All thresholds, TTLs, timeouts, retry counts and windows are named settings or constants (research D-6, D-7, quickstart §1); the 90-day skip is the constant `SKIP_DURATION`. No signals: the status webhook needs no hook because liveness reads `Version` directly (D-4). Use cases decompose into intention-revealing private methods; comments only for *why*.

### XI. Contained Changes — PASS with justified reach (see Complexity Tracking)

Changes outside `retail/opt_in/` are limited to what the spec requires: cart notification flag and idempotency (FR-031/032), coupon-send branch in assign (default template, 100% contact percentage) (FR-005), client options for timeouts and redaction (FR-039/038), log redaction on reused paths (FR-038), flagged-cart retention (A7). Spotted but **not** changed: project-wide correlation id, `CONN_MAX_AGE`, `task_create_template` marking transient failures as `REJECTED`, `print` calls in `IntegrationsClient`, PII in other log lines not on Opt-in paths — reported as follow-ups.

### XII. Specification Traceability — PASS

The spec opens with the mandatory inheritance section pinned to tag `001-new-client-phone-optin-v1.5` (`52d927b`) for both product spec and architecture doc; BD-001 – BD-027 listed; scope = retail-setup. Every decision in research.md cites the FR/BD it serves.

### XIII. No Silent Divergence — PASS

No technical need of retail contradicts the inherited spec. Points checked and found compatible: "already in Opt-in" decided by lookup (BD-026 leaves the socket handling to engineering); send-time approval check against the newest known status (NFR-008); event-only disconnect (clarification 2026-10-01) kept even though it leaves a small race (D-1, recorded); identifier through existing Flows v2 endpoints.

BD-017 / architecture keep delete/rename protection of the **Opt-in** group in Flows, as inherited (confirmed 2026-10-08 as the one Flows-side safety layer besides notifying channel deactivation and sending messages), so there is no divergence. One **internal** inconsistency of this engineering spec (A6 vs FR-016) was resolved in D-24 and A6 was amended; it is not inherited, so it is not a divergence.

### XIV. Version Control, Review & Commits — PASS with the usual branch-name note

Atomic Conventional Commits (≤ 50 chars), PR title ≤ 72 chars with type prefix, PR body with only `## What` / `## Why`. Branch name follows the spec-kit convention (Complexity Tracking).

### XV. Changelog Maintenance — PASS (planned)

`CHANGELOG.md` gets a new MINOR heading with `feat:` entries (Opt-in API, `channel.deleted` consumer, cart `opt_in` flag) at release.

**Gate verdict (pre-research and post-design)**: PASS. No unjustified violation; the items in Complexity Tracking are recorded deviations with justification.

## Flow Integrity & Invariant Review (FIIR)

```
Flow A: merchant save → gates (SA, WhatsApp, fields) → settings row → reconciler → coupon-send agent active/inactive → job 2 eligibility
Flow B: storefront submit → validation → submit row (+completed_at) → job 1 (Flows) → resolved outcome → job 2 (coupon) / job 3 (cart register)
Flow C: Flows channel.deleted → binding channel.deleted.wac → consumer validation → sender match → coupon off + agent inactive
Flow D: abandoned-cart notification (opt_in) → AC enabled? → Opt-in on? → cart register per order form → existing abandonment dispatch
Flow E: template status (webhook | refresh | readiness) → Version.status / confirmed_at → liveness → storefront read (cached) / merchant warning / job 2
```

Invariants:

| Invariant | Enforced where | Assumed where |
|---|---|---|
| I1. Coupon is sent only for a first membership while live, from the sender stored at send time, at most once | job 2 (DB liveness + CAS claim) | `Broadcast.get_current_template` (`broadcast.py:714-727`) only checks `current_version` — so job 2 gates **before** calling it |
| I2. One **effective** coupon-send agent per project (the single agent the role lookup returns), never deleted by Opt-in | role lookup (official first, else child) + `OptInSettings.coupon_send_integrated_agent` + reconciler lock | `assign.py:203-214` would create a second row on re-assign — never used for reactivation; a generic re-assign leaves an inactive leftover row (accepted) |
| I7. A custom agent is resolved only for the official agent it descends from | exact `parent_agent_uuid` filter (applied in order-status and check_agent_active; same rule in the coupon resolver) | `order_status.py:139-143` and `check_agent_active.py:104-109` use `parent_agent_uuid__isnull=False` today |
| I3. Opt-in never creates/activates/deactivates the abandoned-cart automation | save/SA/disconnect use cases touch only the coupon agent | SC-002 test snapshots the AC agent/feature |
| I4. One open flagged cart per order form; flag and Opt-in phone survive unflagged notifications | `CartUseCase` (Opt-in on) + partial unique index | `cart.py:160-167` keyed lookups by phone — changed for Opt-in projects |
| I5. A not-live coupon is indistinguishable from an off coupon on the storefront, and no send happens | single liveness function used by storefront, merchant read and job 2 | `update_template.py:55-58` keeps `current_version` on the old approved version during review — liveness uses the latest version per sender instead |
| I6. "Already in Opt-in" is never inferred from a timeout/5xx/429 | `FlowsContactService` classification + lookup-based decision | `flows/service.py:79-92` collapses failures to `None` — not used by Opt-in |

Branch matrix (dimensions relaxed vs. invariants kept):

| Branch | What changes | Must survive | Intentionally dropped |
|---|---|---|---|
| Coupon on, template pending/rejected/paused | storefront shows no coupon, admin warning | I1, I2, I5; coupon stays on and saved | sends |
| Coupon on, Integrations unreadable > 15 min | status unknown | I1, I5 (fails closed: not live) | sends, coupon copy |
| Sender changed while submit pending | job 2 reads the sender at send time | I1 | old sender |
| SA disabled | coupon-send inactive | I2 (deactivate, not delete), I3; Opt-in and coupon settings unchanged | form availability |
| `channel.deleted` for non-sender / duplicate / other type | nothing | all | — |
| Notification without `opt_in` (any project) | none | today's behavior; I4 for flagged carts | — |
| Notification `opt_in=true`, Opt-in off | flag dropped | today's behavior | flag |
| Flows timeout on submit | outcome pending | I6; `completed_at` kept | synchronous answer |
| Retry finds contact already in Opt-in after a lost create | outcome (c) | I1 (no coupon), I6 | coupon/enrollment for that submit (inherited known limitation) |

Assumptions found downstream (quoted):

- `retail/agents/domains/agent_webhook/services/broadcast.py:726` — `if status == "APPROVED": return template` (on `current_version`) → job 2 gates first (I1/I5).
- `retail/agents/domains/agent_integration/usecases/assign.py:203-208` — `get_or_create(agent=agent, project=project, is_active=True, ...)` → reactivation implemented separately (I2).
- `retail/webhooks/vtex/usecases/cart.py:162-167` — `Cart.objects.get(order_form_id=..., project=..., phone_number=phone, status="created")` → order-form-scoped lookup for Opt-in projects (I4).
- `retail/vtex/tasks.py:400-401` — `Cart.objects.filter(created_on__lt=time_threshold).delete()` → unflagged carts keep the 15-day purge; flagged carts are purged after `OPT_IN_CART_RETENTION_DAYS` (30).
- `retail/templates/tasks.py:64` — `payload = {"version_uuid": version_uuid, "status": "REJECTED"}` on any exception → readiness asks Integrations instead of trusting local `REJECTED`.
- `retail/agents/domains/agent_webhook/usecases/order_status.py:139-143` — `IntegratedAgent.objects.get(parent_agent_uuid__isnull=False, project=project, is_active=True)` → would resolve a coupon child as the order-status agent; fixed to `parent_agent_uuid=settings.ORDER_STATUS_AGENT_UUID` (I7); same in `check_agent_active.py:106`.

Gaps / verdict: **PASS** for the design. Each assumption above has a matching change and a test in the IX table.

## Project Structure

### Documentation (this feature)

```text
specs/005-shopper-phone-optin/
├── spec.md
├── plan.md                                   # this file
├── research.md                               # D-1 … D-24 + codebase findings F1–F14
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── opt-in-api.openapi.yaml               # new HTTP endpoints, contract v1.0.0
│   ├── abandoned-cart-notification.md        # additive `opt_in` flag
│   ├── flows-channel-deleted-event.md        # consumed EDA event
│   ├── flows-outbound.md                     # retail → Flows
│   ├── integrations-outbound.md              # retail → Integrations
│   └── coupon-send-agent-lambda.md           # official coupon-send agent payload/response, rules for custom children
├── checklists/requirements.md
└── tasks.md                                  # /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
retail/
├── opt_in/                                           # NEW app
│   ├── apps.py · models.py · constants.py · exceptions.py · checks.py (opt_in.E001)
│   ├── cache.py                                      # storefront cache, locks, Flows breaker (django.core.cache)
│   ├── handle.py                                     # registers ChannelDeletedConsumer
│   ├── tasks.py                                      # resolve submit, coupon, enroll, identifier, reconcile, refresh, sweeper, cleanup
│   ├── migrations/0001_initial.py
│   ├── api/  views.py · serializers.py · permissions.py (IsStorefrontRetailToken) · urls.py
│   ├── consumers/  channel_deleted_consumer.py · channel_deleted_event_parser.py
│   ├── usecases/
│   │   ├── dto.py
│   │   ├── get_merchant_settings.py · save_merchant_settings.py · record_shopping_assistant_state.py
│   │   ├── get_storefront_settings.py · coupon_liveness.py
│   │   ├── get_eligibility.py · record_skip.py · promote_browser_state.py · email_normalizer.py
│   │   ├── accept_submit.py · resolve_submit_contact.py · whatsapp_identity.py
│   │   ├── send_coupon.py · enroll_cart.py · fill_contact_identifier.py
│   │   ├── ensure_opt_in_contact_group.py
│   │   ├── reconcile_coupon_send.py · coupon_send_agent_resolver.py · activate_coupon_send.py · deactivate_coupon_send.py · template_alignment.py
│   │   ├── refresh_coupon_template_status.py
│   │   ├── handle_channel_deleted.py
│   │   └── redispatch_submits.py
│   ├── services/  flows_contact_service.py · whatsapp_channels_service.py · coupon_template_status_service.py
│   ├── management/commands/  opt_in_redispatch_submits.py
│   └── tests/  (api/, usecases/, services/, consumers/, tasks/, test_checks.py, pii_assertions.py)
├── agents/
│   ├── shared/cache.py                                               # MOD AgentRole.OPT_IN_COUPON + ROLE_SETTING_NAMES
│   ├── domains/agent_integration/usecases/assign.py                  # MOD default coupon template branch (config opt_in_role=coupon), 100% contact percentage, display name
│   ├── domains/agent_integration/usecases/build_opt_in_coupon_translation.py  # NEW pt/en/es default template
│   ├── domains/agent_webhook/usecases/order_status.py                # prerequisite on main (PR #590): parent lookup by exact ORDER_STATUS_AGENT_UUID — not part of this feature's diff
│   ├── domains/agent_webhook/usecases/webhook.py                     # MOD PII-free log lines (Lambda response, data=)
│   ├── domains/agent_webhook/services/active_agent.py                # MOD PII-free log line (Payload:)
│   └── domains/agent_webhook/services/broadcast.py                   # MOD PII-free log lines (Data:/Response:)
├── api/vtex_projects/usecases/check_agent_active.py                  # prerequisite on main (PR #590): custom order-status check by exact parent — not part of this feature's diff
├── clients/
│   ├── base.py                                                       # MOD redact_payload option, DEFAULT_REQUEST_TIMEOUT_SECONDS
│   ├── flows/client.py                                               # MOD ctor options; fields endpoints; update_contact_fields
│   ├── integrations/client.py                                        # MOD ctor options; list_whatsapp_cloud_channels; get_template_by_name
│   └── vtex_io/client.py                                             # MOD ctor options (timeout, redaction)
├── interfaces/clients/{flows,integrations}/interface.py              # MOD protocol methods
├── observability/pii.py                                              # NEW mask_phone, opaque_user_id
├── webhooks/vtex/
│   ├── serializers.py                                                # MOD CartSerializer.opt_in (optional, default False)
│   ├── usecases/dto.py                                               # MOD ProcessAbandonedCartNotificationDTO.opt_in
│   ├── usecases/process_abandoned_cart_notification.py               # MOD effective opt-in; masked logs
│   ├── usecases/cart.py                                              # MOD order-form idempotency for Opt-in projects; masked logs
│   ├── views/abandoned_cart_notification.py                          # MOD pass opt_in into the DTO
│   └── services_cart_abandonment_unified.py                          # MOD PII-free log lines only
├── vtex/
│   ├── models.py                                                     # MOD Cart.opt_in + partial unique constraint
│   ├── migrations/0016_cart_opt_in.py                                # NEW (non-atomic, concurrent index)
│   └── tasks.py                                                      # MOD cleanup keeps flagged carts until retention
├── event_driven/handle.py                                            # MOD register opt_in consumers
├── settings.py                                                       # MOD INSTALLED_APPS, OPT_IN_* settings, routes, beat
└── urls.py                                                           # MOD path("api/v3/opt-in/", include("retail.opt_in.api.urls"))
```

**Structure Decision**: a new domain app `retail/opt_in/` following the `retail/broadcasts/` layout (api/, consumers/, handle.py, services/, usecases/, tasks.py), because Opt-in owns models, HTTP endpoints, an EDA consumer and Celery tasks. Infrastructure services specific to Opt-in's failure semantics live in `retail/opt_in/services/`; shared clients are extended in place in `retail/clients/` with backward-compatible constructor options.

## External dependencies and deployment

| Owner | Item | Blocking for |
|---|---|---|
| Infra | Queue `retail.flows-channel-deleted` (quorum, delivery limit, DLX) bound to `flows-channel-events.topic` / `channel.deleted.wac`; worker deployments `opt-in-contact`, `opt-in-followup` with HPA; new env vars | disconnect handling; background work |
| Flows | Role limited to notifying channel deactivation, sending messages and, as inherited (BD-017), protecting the **Opt-in** group against delete/rename. Configuration: `CHANNEL_EVENTS_PUBLISH_ENABLED=true` and `USE_EDA` on (the publisher needs both; delivery is best effort, research D-1). Verification (no change) of existing v2 endpoints used for the identifier and of WhatsApp URN normalization — see Open items | FR-009, FR-021a, FR-034, BD-017 |
| Integrations | none new (both routes exist); confirm template list returns translation `status`, `body`, `header`, `footer`, `buttons` for `names=` | readiness check |
| agentic-cx | mint the storefront retail JWT with `vtex_account` + validated `user_email`; forward `opt_in`; write SA state on every change and backfill before release (A8); call `PUT /settings/` through the merchant proxy | every storefront and merchant flow |
| Official agents (Lambda code) | implement and push the official coupon-send agent following [contracts/coupon-send-agent-lambda.md](./contracts/coupon-send-agent-lambda.md); set `OPT_IN_COUPON_AGENT_UUID` per environment | coupon |
| Ops | as part of the PR #590 rollout (already on `main`), confirm that every existing `parent_agent_uuid` equals `ORDER_STATUS_AGENT_UUID` (quickstart §2) | order-status custom agents keep resolving |

## Open items for confirmation (do not block `/speckit-tasks`)

1. ~~Flagged-cart retention~~ — resolved 2026-10-08: 30 days for flagged carts, 15 days for the rest (D-8).
2. ~~A6 wording~~ — resolved 2026-10-08: spec A6 amended (D-24).
3. ~~Brazilian 9th-digit wa_id and existing v2 endpoints~~ — verified against the Flows code on 2026-10-09: endpoint behaviors confirmed and folded into D-9a, D-13, D-25 and contracts/flows-outbound.md (identifier fill now updates by contact UUID, not URN); `channel.deleted` delivery is best effort (D-1); the 9th-digit finding became Open item 6.
4. ~~Opt-in group delete/rename protection~~ — resolved 2026-10-08: stays in Flows as inherited (BD-017); no divergence.
5. ~~Child lookup scope (F15)~~ — resolved by [PR #590](https://github.com/weni-ai/retail-setup/pull/590) (`fix: Scope order-status child lookup to its official parent`, merged to `main` and brought into this branch on 2026-10-09): exact parent UUID in `order_status.py` and `check_agent_active.py`, with tests (`test_order_status_parent_agent_scope.py`). Pre-deploy data check belongs to that PR's rollout. Original finding: `order_status.py:139-143` and `check_agent_active.py:104-109` filter children with `parent_agent_uuid__isnull=False`. Once coupon-send children exist, a project without an official order-status agent would resolve a coupon child as its order-status agent; a project with one order-status child and one coupon child would raise `multiple_parent_agents` and stop order-status; `check_agent_active("order_status")` would answer `True` wrongly. Proposed: filter by the exact parent UUID (same lookup, only scoped), with the pre-deploy data check.
6. ~~Brazilian 9th digit in the contact lookup~~ — decided 2026-10-09: keep the exact key of FR-019/architecture. Accepted risk: a BR contact stored without the 9 (inbound-created) is not matched, so a second WhatsApp contact is created and the shopper may be treated as a first membership. Measured through a log marker on `created` outcomes for `55` numbers (research D-6a).

## Complexity Tracking

| Item | Why it is needed | Simpler alternative rejected because |
|---|---|---|
| Coupon send does not auto-retry ambiguous failures (read timeout after send, 5xx); they become `failed_ambiguous` and are re-dispatched by an operator (IV) | FR-029 forbids more than one coupon per first membership, and Flows `whatsapp_broadcasts` exposes no idempotency key, so the operation cannot be made idempotent from retail's side. Unambiguous failures (connection before send, 429) are retried; the failure stays recorded and re-dispatchable, satisfying IV's exhaustion clause | Auto-retrying would risk duplicate coupons; not sending at all would drop data without a trace |
| Log-line changes in shared modules (`RequestClient`, `ActiveAgent`, `AgentWebhookUseCase`, `Broadcast`, `CartUseCase`, `ProcessAbandonedCartNotificationUseCase`, `CartAbandonmentService`) (XI) | Opt-in data must flow through these paths (FR-030 "same processing", D-3 agent Lambda pipeline, A1 "regular broadcast path"), and they log phones, emails and payloads today. FR-038/SC-010 and constitution VII forbid that. Changes are log-content-only, plus an opt-in `redact_payload` flag whose default keeps current behavior | Duplicating the cart and broadcast pipelines for Opt-in would fork business logic; leaving the lines would violate FR-038 |
| Cart idempotency per order form applies only when Opt-in is on for the project | FR-031 requires today's behavior to stay identical for callers without the flag; scoping the new lock/lookup to Opt-in projects keeps every other project byte-for-byte unchanged | Switching every project to order-form locking would change concurrency behavior for all stores |
| `task_cleanup_old_carts` purges flagged carts after `OPT_IN_CART_RETENTION_DAYS` (30) and keeps 15 days for the rest | A7/BD-012: retail keeps the attribution data; 30 days bounds storage given thousands of carts per day (decided 2026-10-08) | Leaving the purge untouched deletes flagged carts after 15 days; an open-ended retention grows without bound |
| Branch `005-shopper-phone-optin` instead of `feature/<kebab>` (XIV) | Created by the spec-kit `before_specify` hook; same precedent as specs 002–004 | Renaming mid-feature breaks the branch ↔ `specs/<id>/` association |
