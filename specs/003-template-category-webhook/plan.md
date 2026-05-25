# Implementation Plan: Direct Send Template Incorrect-Category Webhook

**Branch**: `003-template-category-webhook`
**Date**: 2026-05-24
**Spec**: [./spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-template-category-webhook/spec.md`

## Summary

Expose a new internal POST webhook
(`/webhook/templates-status/api/category-notification/`) that
Integrations calls when Meta-side category-detection determines that
a Direct Send template's category is wrong. The webhook fans out
across every `IntegratedAgent` linked to the named project + app and
flips each matched `Template.current_version.status` to `FLAGGED`
when the spec's two-clause flagging condition fires
(`template_category != template_correct_category` OR
`template_category != "UTILITY"`). Spec 002's pre-existing dispatch
gate (`Broadcast.get_current_template` at
`retail/agents/domains/agent_webhook/services/broadcast.py:665-676`)
already skips broadcasts for any non-`APPROVED` Version, so the
`FLAGGED` write is immediately effective at the next dispatch
attempt with no broadcast-path change required by this feature.

The technical approach (resolved in `./research.md`) is:

1. **New view** `DirectSendCategoryWebhook` (an `APIView` with
   `permission_classes = [CanCommunicateInternally]`) lives under
   `retail/webhooks/templates/views/direct_send_category.py`,
   alongside the existing `TemplatesStatusWebhook`. A new URL entry
   in `retail/webhooks/templates/urls.py` exposes it at
   `templates-status/api/category-notification/`. The view is thin —
   it validates the payload via a new `DirectSendCategoryWebhookSerializer`,
   builds a frozen `DirectSendCategoryDTO` (`@dataclass(frozen=True)`),
   delegates to the use case, and returns the HTTP response (Constitution
   Principle I — Views layer).
2. **New use case** `DirectSendCategoryWebhookUseCase` lives under
   `retail/webhooks/templates/usecases/direct_send_category.py`. It
   owns the ORM lookups (IntegratedAgents by `(project, app_uuid)`,
   Template by `(integrated_agent, name)`), the flagging-condition
   evaluation, and the `Version.status = "FLAGGED"` write. It is
   framework-agnostic (no `rest_framework` imports), raises only
   domain or DRF exceptions (`ValidationError` etc.), and emits every
   audit-log line via a private helper that bakes in the
   `[DirectSendCategoryWebhook]` tag (FR-009 / FR-009a–e). The
   `received` line emits before any DB lookup; the `completed` line
   emits at the success-path exit with the same two counters the
   HTTP response body carries (FR-009c, FR-010); the
   `unexpected_error` line replaces `completed` on the
   caught-exception path with `exc_info=True` (FR-009b).
3. **No new model, no new column, no migration**. The `FLAGGED`
   value is already on `Version.STATUS_CHOICES`
   (`retail/templates/models.py:58`, shipped by spec 002's migration
   `0017_alter_version_status_paused_flagged`). The lookup uses the
   pre-existing FK chain
   `IntegratedAgent ← Template ← Version` plus the
   `Version.integrations_app_uuid` column already populated at
   template-creation time by
   `retail.templates.usecases._base_template_creator._create_version`
   (Decision 2 / `data-model.md §2`).
4. **Idempotency** is achieved by a two-path dispatch inside the
   use case: when the matched `Version.status == "FLAGGED"`
   already, the use case branches on the FR-006 flagging condition
   — (a) condition true → emit `flag_replay_noop` and skip the
   `UPDATE` (replay of an existing flag); (b) condition false → call
   `_demote_version` to write `status = "APPROVED"` and emit
   `auto_demoted` (the corrected-category recovery channel per
   FR-006c / FR-007c clause (b) / FR-007d). The same convergence
   property holds in the reverse direction: replays of the
   corrected-category payload against a Version already in
   `APPROVED` follow the `no_action_required` path (FR-006 no-fire).
   No dedup cache, no distributed lock (FR-008a; Decision 5).
5. **Cross-tenant isolation** is enforced at the SQL level: the
   IntegratedAgent queryset filters on BOTH `project.uuid == payload.project_uuid`
   AND a join through `templates.versions` with
   `integrations_app_uuid == payload.app_uuid`. A coincidental
   `app_uuid` match on a Version in a different project is excluded
   by the tenant clause (FR-004 / SC-006 / Decision 3).
6. **Response shape** is `{detail, templates_updated, integrated_agents_inspected}`
   on every HTTP 200 path — including the
   `no_matching_integrated_agent` / `template_not_found` /
   `no_action_required` cases (counters degrade to zero). HTTP 400
   surfaces serializer validation failures; HTTP 500 surfaces
   genuinely unexpected exceptions (FR-010, FR-010a, FR-010b).

## Technical Context

**Language/Version**: Python 3.10 (`pyproject.toml` `python = "^3.10"`).

**Primary Dependencies**: Django 5.0, Django REST Framework 3.15,
`mozilla-django-oidc` (used transitively via `CanCommunicateInternally`'s
`IsAuthenticated` base — no direct OIDC code path in this feature).
The new webhook depends on the existing
`retail.internal.permissions.CanCommunicateInternally` class and the
existing `Version` / `Template` / `IntegratedAgent` / `Project` ORM
models. No new third-party dependency is introduced.

**Storage**: PostgreSQL via `psycopg2`. **Zero schema changes**.
No new column, no new index, no new constraint, no new table. The
single `UPDATE` touches `templates_version.status` only, on rows
already keyed by the existing PK.

**Testing**: `django.test.TestCase` + `unittest.mock` (`MagicMock`,
`patch`). New test files under
`retail/webhooks/templates/tests/usecases/test_direct_send_category.py`
and `retail/webhooks/templates/tests/views/test_direct_send_category.py`.
A new `__init__.py` is created at
`retail/webhooks/templates/tests/__init__.py` (the existing webhook
has no tests at all — Constitution Principle III treats this as a
coverage gap for *new* code, not a backfill obligation for the
legacy webhook; see Complexity Tracking). `coverage` 7.8 + the
project's `contrib/compare_coverage.py` parity check.

**Target Platform**: Linux (containerized service, `docker/`). The
webhook is an internal-only endpoint behind the network boundary;
Retail's existing internal-auth middleware is the only access gate.

**Project Type**: web-service (Django + DRF backend; this feature
adds one POST endpoint to the existing `retail.webhooks.templates`
URL namespace).

**Performance Goals**:

- Per-request latency: p99 < 500ms in steady state (spec SC-007).
  The hot path is two read queries (IntegratedAgent fan-out, then
  per-agent Template lookup) plus N single-row `UPDATE`s where N =
  number of matched IntegratedAgents (typically 1; multi-agent
  fan-out is the exception per US1 scenario 4). The realistic
  traffic profile is sparse (≤1 req/min steady state; bursts of
  ≤10 req/sec during a rare Meta-driven mass re-categorization
  event — operator-driven, not user-driven), so throughput is not
  a release gate and no PR-time load test is required.
- No outbound HTTP. The webhook is purely a DB consumer; no
  service / client layer is introduced (Decision 7).
- Flag-effective-by-next-dispatch: SC-001 = 1 second from HTTP
  200 to the `FLAGGED` write being visible (the write is committed
  inside the request transaction; the SLA is essentially "round-trip +
  one row update").

**Constraints**:

- **Backward compatibility — existing webhook untouched (FR-001)**:
  The existing `TemplatesStatusWebhook` (`templates-status/api/notification/`)
  is read-only for this feature. Its view, serializer, use case,
  URL entry, log format, and response shape are bit-identical to
  pre-feature. The new endpoint sits next to it (different path:
  `templates-status/api/category-notification/`) so operators find
  both webhooks under one namespace. A snapshot test on
  `retail/webhooks/templates/urls.py` is NOT required because the
  existing entry is preserved verbatim and `urls.py` is small enough
  to review by hand.
- **Pre-existing dispatch gate untouched (FR-013)**: This feature
  writes `FLAGGED` and depends on spec 002's
  `Broadcast.get_current_template` skipping the broadcast for any
  non-`APPROVED` Version. The dispatch-gate code at
  `retail/agents/domains/agent_webhook/services/broadcast.py:665-676`
  MUST NOT be modified. The integration test (`tasks.md` T019)
  verifies the end-to-end behavior: webhook fires → `FLAGGED`
  written → next order-status webhook for the same template is
  skipped.
- **Two convergent demote channels (FR-014, post-2026-05-25)**:
  This webhook transitions `* → FLAGGED` on the flag branch
  (FR-007) and `FLAGGED → APPROVED` on the auto-demote branch
  (FR-006c / FR-007d) when a corrected-category payload
  (`template_category == template_correct_category == "UTILITY"`)
  arrives for an already-`FLAGGED` Version. The operator-driven
  `UpdateTemplateUseCase` at
  `retail/templates/usecases/update_template.py:46-64` remains
  available as a second, manual recovery channel. Both channels
  converge on `Version.status = "APPROVED"` via a single-row
  `UPDATE`, never change the Template's `current_version` pointer
  (FR-007a preserved on the demote write), and never create a new
  Version row. Auto-demote fires regardless of how the prior
  `FLAGGED` was originally set, per Assumption A11 — operators
  needing a non-recoverable broadcast block should use a different
  `Version.status` value (e.g. `PAUSED` or `REJECTED`) which is
  NOT affected by this webhook.
- **Audit log shape pinned to `[DirectSendCategoryWebhook] <event_name>: <k=v> ...` (FR-009)**:
  The closed enumeration of `event_name` tokens is the contract
  surface for operator dashboards (FR-009a). New tokens MAY be added
  in future PRs (additive-only); existing tokens MUST NOT be renamed
  or removed. The legacy `TemplatesStatusWebhook`'s unprefixed
  free-form format is NOT to be used by this webhook (Clarifications
  session 2026-05-24 / Pattern B). Log-level discipline mirrors
  `[ORDER_STATUS]` (`retail/vtex/tasks.py:113-177`): INFO for happy
  path / state transitions / replays, WARNING for "expected but
  unhappy" lookup misses, ERROR with `exc_info=True` for
  `unexpected_error` only (FR-009b). The `reason=<sub_reason>` k=v
  on `flagged` events draws from the closed enumeration
  `{category_mismatch, category_not_utility, category_mismatch_and_not_utility}`
  per FR-006b / FR-009a.
- **Tenant isolation (FR-004 / SC-006 / Decision 3)**: The
  IntegratedAgent queryset filters on `project.uuid == payload.project_uuid`
  AND requires at least one `Version` with
  `integrations_app_uuid == payload.app_uuid` on one of that
  IntegratedAgent's Templates. A coincidental `app_uuid` match in a
  different project is excluded by the tenant clause; the audit log
  records `no_matching_integrated_agent` for the named project
  without leaking any reference to the other tenant's IntegratedAgent.
- **No new env var or settings key (FR-001 — implicit)**: The
  webhook reuses `CanCommunicateInternally`'s existing auth
  configuration (the same Django permission code-name
  `can_communicate_internally` used by `TemplatesStatusWebhook`).
  Deploying this feature without any settings change is safe.
- **Idempotency without a dedup cache (FR-008 / FR-008a / Decision 5)**:
  No Redis SETNX, no LocMemCache wrapper. The idempotency contract
  is satisfied by the early-return guard inside the use case
  (`if version.status == "FLAGGED": emit flag_replay_noop; continue`).
  Concurrent webhook calls for the same `(project, app, template)`
  tuple converge on the same final state through Django's default
  transaction isolation (Edge Case row in spec.md). The dedup
  surface for the OrderStatus broadcast pipeline (spec 002's
  FR-028 cache) is unrelated and untouched.
- **No new database migration (A10)**: The `FLAGGED` enum value
  already exists. The feature ships zero migrations across all apps.
- **PR coverage cannot decrease** (Constitution Principle III). The
  new view + use case must be covered by unit and integration tests
  in the same PR; the existing-webhook coverage gap is documented in
  Complexity Tracking and is NOT a backfill obligation of this PR.

**Scale/Scope**:

- Steady-state request volume: ≤1 webhook per minute across the
  entire fleet — category re-detections from Meta are operator-driven
  (a human reviewing a template and re-classifying it), not
  user-driven, so the rate is bounded by manual review cadence
  rather than message traffic. Burst capacity: ≤10 webhook calls
  per second during a rare Meta-driven mass re-categorization
  event (multiple templates re-classified in a single batch).
  Both are far below any throughput ceiling worth load-testing —
  the earlier 50–200 req/sec estimate (mirroring spec 002's
  order-status broadcast peak) was an over-estimate because that
  peak applies to user-driven order events, not operator-driven
  category determinations.
- Active IntegratedAgents linked to a single `(project, app_uuid)`
  pair: typically 1 (one active OrderStatus IntegratedAgent per
  WhatsApp channel); the multi-IntegratedAgent fan-out (US1 scenario
  4) is exceptional and reflects historical inactive assignments
  that share the same `app_uuid`.
- Code surface: ~6 files modified or added (3 production: view,
  use case, urls.py one-line addition, serializer; 3 test files;
  one tests `__init__.py`). No new app, no new model, no new
  migration.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1
design. Reference: `.specify/memory/constitution.md` (v1.0.0).*

### I. Layered Clean Architecture (NON-NEGOTIABLE) — PASS

- **Views layer**: `DirectSendCategoryWebhook` is a thin DRF
  `APIView`. It validates the payload via `DirectSendCategoryWebhookSerializer`,
  builds a frozen `DirectSendCategoryDTO`, delegates to the use
  case, and shapes the HTTP `Response`. It calls no `Model.objects.*`,
  carries no business logic, and imports no infrastructure clients.
  Authorization is expressed exclusively via
  `permission_classes = [CanCommunicateInternally]` (no
  `self.check_object_permissions(...)`, no `if request.user...`).
- **Use Cases layer**: `DirectSendCategoryWebhookUseCase` holds
  every business rule (flagging condition, idempotency early-return,
  fan-out across IntegratedAgents), every ORM query
  (`IntegratedAgent.objects.filter(...).distinct()`,
  `agent.templates.filter(name=...).select_related("current_version")`,
  `version.save(update_fields=["status"])`), and every audit-log
  emission. The use case raises only domain exceptions (none in v1
  — the spec mandates HTTP 200 for every well-formed request) and
  is framework-agnostic (no `rest_framework` imports, no `Request` /
  `Response` use, no permission checks).
- **Services layer**: Not introduced. The webhook performs no
  outbound HTTP and wraps no client (Decision 7). The pre-existing
  Service layer is untouched.
- **Clients layer**: Not introduced. Same rationale as Services
  layer.
- **Interfaces layer**: Not introduced. Same rationale.

### II. DRF Composition for AuthN/AuthZ — PASS

- The new endpoint declares `permission_classes = [CanCommunicateInternally]`
  on the view class. This is identical to the existing
  `TemplatesStatusWebhook` (Decision 1) and is the canonical
  internal-auth gate for webhooks called by Integrations.
- No permission logic appears inside the view method body or inside
  the use case.
- `CanCommunicateInternally` already inherits from
  `permissions.IsAuthenticated` (`retail/internal/permissions.py:12`),
  so composition with `&`/`|` is structurally supported. The
  feature does not require composition (single permission class is
  sufficient), so the declaration is a flat list.
- No `HasProjectPermission` check is added: the caller is a trusted
  internal service (Integrations), not an end-user operator. The
  payload itself carries the `project_uuid` that gates the lookup
  (FR-002).

### III. Test Coverage Parity & Isolated Tests (NON-NEGOTIABLE) — PASS (with planned tests)

Every new code branch will be exercised by tests in the same PR
(`tasks.md` will enumerate them). Notable points:

- **Use case tests** (`test_direct_send_category.py` in
  `retail/webhooks/templates/tests/usecases/`): cover all 10 event-name
  branches from FR-009a (`received`, `flagged` ×3 reasons,
  `flag_replay_noop`, `no_action_required`, `auto_demoted`,
  `no_matching_integrated_agent`, `template_not_found`,
  `template_has_no_current_version`, `completed`, `unexpected_error`).
  The flagging-condition truth table (FR-006) is pinned by four
  parametrized scenarios covering the four (match / mismatch) ×
  (UTILITY / non-UTILITY) cells; the auto-demote branch is pinned
  by a scenario that pre-seeds the Version as `FLAGGED` and fires
  the `UTILITY/UTILITY` payload, asserting the Version is rewritten
  to `APPROVED` and the audit line is `auto_demoted` with
  `previous_status=FLAGGED new_status=APPROVED` and no `reason`
  key.
- **View tests** (`test_direct_send_category.py` in
  `retail/webhooks/templates/tests/views/`): cover the HTTP 200 /
  400 / 401 / 500 boundary (FR-010, FR-010a, FR-010b). The
  internal-auth gate is exercised by sending the request as a user
  with and without `can_communicate_internally` permission (mirroring
  `retail.internal.test_mixins.BaseTestMixin.setup_internal_user_permissions`).
- **Integration test** (`tasks.md` T019): end-to-end via Django's
  test client — webhook fires, `FLAGGED` written, next dispatch
  attempt for the same template skipped by the existing
  `Broadcast.get_current_template` gate. This pins the integration
  with spec 002's dispatch path without modifying that path.
- **No `# pragma: no cover` required**: every code branch has a
  finite, in-process exercisable test path. No live external
  provider is involved.
- **Cache isolation**: the use case does not touch the cache, so
  the `LocMemCache` override pattern is not required for this
  feature's tests (the `BaseTestMixin._setup_test_cache` is used by
  the view tests transitively if needed to keep the existing
  `Project.clear_cache` signal noise out of the test surface).

### IV. Self-Documenting Code — PASS

- Method names carry intent (`_emit_received`, `_emit_completed`,
  `_evaluate_flagging_condition`, `_flag_version`,
  `_log_unexpected_error`, `_lookup_integrated_agents`,
  `_lookup_template`, `_is_already_flagged`,
  `_determine_flagging_reason`).
- The `[DirectSendCategoryWebhook]` log helper is the only point in
  the code that knows the log-line shape — every event emission
  routes through it, so the FR-009 format is enforced structurally
  (no `logger.info(f"[DirectSendCategoryWebhook] ...")` scattered
  across the codebase).
- Docstrings are reserved for non-obvious *why* (e.g. why the
  reason enumeration is composite for `category_mismatch_and_not_utility`,
  why the IntegratedAgent lookup includes `is_active=False`, why
  the idempotency contract does not require a dedup cache).
- Logging f-string identifiers always carry both tenant identifiers
  in scope (`project_uuid`, `app_uuid`, plus `integrated_agent_uuid`
  / `template_uuid` / `version_uuid` per FR-009d). Single Level of
  Abstraction is preserved by extracting the audit-log emission
  into the private helper instead of inlining `logger.info(...)`
  in the dispatch flow.
- Per-event log methods (one method per `event_name` token) keep
  each emission at a single level of abstraction; the dispatch flow
  reads as `emit_received(); lookup(); fanout(); emit_completed()`
  without inline string formatting.

### V. Conventional Commits & Structured PRs — PASS

- Branch: `003-template-category-webhook` (spec-kit numeric-prefix
  convention auto-generated by the `before_specify` git hook,
  consistent with spec 002's `002-direct-send-broadcasts` — same
  trade-off accepted in spec 002's plan and documented in
  Complexity Tracking below).
- PR title (≤72 chars): `feat: add Direct Send template category webhook` (49 chars).
- PR description follows the `## What` / `## Why` template.
- No new model is added by this feature, so the "integer PK +
  `uuid (unique=True)`" pattern for new models (Constitution
  Principle V) does not apply. The existing `Version` /
  `IntegratedAgent` / `Template` models keep their legacy UUID PKs
  unchanged.

### Constitution Check verdict

**No violations.** The plan does not require entries in
`Complexity Tracking` for principle violations. The Complexity
Tracking table below records two non-violation items for
auditability:

1. The legacy `TemplatesStatusWebhook` has no existing tests; this
   feature does NOT backfill them (out of scope) and the existing
   webhook's `urls.py` entry is preserved verbatim.
2. Branch-name deviation from Principle V's `<type>/<kebab>` form
   (same trade-off as spec 002).

The Constitution Check was re-evaluated after Phase 1 design
(data-model, contracts, quickstart) and the verdict stands.

## Project Structure

### Documentation (this feature)

```text
specs/003-template-category-webhook/
├── plan.md                                       # This file (/speckit-plan command output)
├── research.md                                   # Phase 0 — design decisions resolved
├── data-model.md                                 # Phase 1 — persisted state changes (zero schema change)
├── contracts/
│   └── direct-send-category-webhook.md           # Inbound webhook contract (Integrations → Retail)
├── quickstart.md                                 # End-to-end happy-path validation script
├── checklists/
│   └── requirements.md                           # Existing — created during /speckit-specify
├── spec.md                                       # Feature specification (/speckit-specify output)
└── tasks.md                                      # Phase 2 output (NOT created by /speckit-plan)
```

### Source Code (repository root)

The feature adds new files under
`retail/webhooks/templates/` only. Files marked **NEW** are added;
**MOD** is modified in place; everything else is read-only context.

```text
retail/
├── webhooks/
│   └── templates/
│       ├── serializers.py                                                  # MOD — add DirectSendCategoryWebhookSerializer
│       ├── urls.py                                                         # MOD — one new path() entry
│       ├── usecases/
│       │   ├── template_status_update.py                                   # untouched (legacy webhook)
│       │   └── direct_send_category.py                                     # NEW — DirectSendCategoryDTO + DirectSendCategoryWebhookUseCase + result DTO + audit-log helper
│       ├── views/
│       │   ├── template_status_update.py                                   # untouched (legacy webhook)
│       │   └── direct_send_category.py                                     # NEW — DirectSendCategoryWebhook APIView
│       └── tests/                                                          # NEW (the existing webhook has no tests; this folder is created for the new webhook's tests only)
│           ├── __init__.py                                                 # NEW — empty
│           ├── usecases/
│           │   ├── __init__.py                                             # NEW — empty
│           │   └── test_direct_send_category.py                            # NEW — unit tests for DirectSendCategoryWebhookUseCase
│           └── views/
│               ├── __init__.py                                             # NEW — empty
│               └── test_direct_send_category.py                            # NEW — view tests (auth, payload shape, HTTP boundary)
└── (no new migration — the FLAGGED enum value already exists on Version.STATUS_CHOICES from spec 002's migration 0017)
```

**Structure Decision**: this feature lands entirely under the
existing `retail/webhooks/templates/` namespace, mirroring the
existing `TemplatesStatusWebhook`'s file layout
(`views/<name>.py`, `usecases/<name>.py`, `serializers.py`). The
choice keeps both Direct Send-related template webhooks
(`templates-status/api/notification/` for status updates,
`templates-status/api/category-notification/` for incorrect-category
detections) discoverable under one directory, which matches the
spec's FR-001 placement rule and the existing operator mental model
for "template webhooks". No new app is introduced; no new top-level
package is created.

The `tests/` folder is created NEW under
`retail/webhooks/templates/` because the existing webhook has no
tests today. The new folder is scoped to the new webhook's tests
only — backfilling tests for the legacy webhook is explicitly out
of scope (Complexity Tracking below).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations. The two items below are recorded for
auditability — a pre-existing test-coverage gap on the legacy
webhook (out of scope) and a workflow-driven branch-name deviation
from Constitution Principle V (same precedent as spec 002).

| Issue | Why it is acceptable | Simpler alternative rejected because |
|-------|----------------------|--------------------------------------|
| The legacy `TemplatesStatusWebhook` (`retail/webhooks/templates/views/template_status_update.py` + `retail/webhooks/templates/usecases/template_status_update.py`) has no automated tests today (`retail/webhooks/templates/tests/` does not exist before this feature). This feature does NOT backfill tests for the legacy webhook. | Constitution Principle III's coverage-parity rule scopes to NEW or MODIFIED code in the PR. The legacy webhook is read-only context for this feature — its view, serializer, use case, and URL entry are bit-identical pre- and post-feature. Bundling a legacy-webhook test backfill would expand the PR surface, conflate two unrelated change vectors (the new webhook's correctness + the legacy webhook's regression safety), and make `contrib/compare_coverage.py` parity reporting ambiguous (was the lift from the new webhook or from the backfill?). The legacy test backfill is captured as a follow-up PR scoped to `test/templates-status-webhook-tests`. | Backfilling tests for the legacy webhook in this PR would force every reviewer through ~150 lines of test setup that has nothing to do with the new feature; the legacy webhook is operationally stable and is not at risk of silent regression during this feature's PR. |
| Branch name is `003-template-category-webhook` (spec-kit numeric-prefix convention) rather than the Constitution Principle V form `feature/<kebab-description>`. | The numeric-prefix form is created automatically by the spec-kit `before_specify` git hook (`.specify/extensions.yml`) and is the convention documented in `docs/SPEC_KIT.md` for every spec-driven feature in this repo (precedent: spec 002's `002-direct-send-broadcasts` branch, same trade-off accepted in `specs/002-direct-send-broadcasts/plan.md` §Complexity Tracking row 3). Reusing the auto-generated branch keeps the spec-kit artifacts, the git history, and the PR metadata co-located under a single identifier (`003-…`). | Renaming the branch to `feature/template-category-webhook` mid-feature would break the spec-kit tooling's branch ↔ `specs/<id>/` association and force a manual rename of every cross-reference in `spec.md` / `plan.md` / `tasks.md`. A constitution amendment to formally codify the spec-kit exemption is a separate, repo-wide change that does not belong in this feature's PR. |
