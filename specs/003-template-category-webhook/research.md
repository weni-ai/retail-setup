# Phase 0 Research: Direct Send Template Incorrect-Category Webhook

**Feature**: `003-template-category-webhook`
**Date**: 2026-05-24
**Spec**: `./spec.md`

This document records the design decisions taken to remove every
`NEEDS CLARIFICATION` from the plan and the alternatives rejected on
the way. Every decision is sized so a single PR can implement it
without reopening this file. Decisions are organized in the order an
implementer encounters them while reading `plan.md` top-to-bottom.

The spec carried zero `NEEDS CLARIFICATION` markers at planning
time (the user's description was contract-shaped: 5 fields, 2-clause
flagging condition, `FLAGGED` target state). The Clarifications
session 2026-05-24 (folded into `spec.md` §Clarifications) pinned the
audit-log shape to the `[TAG] event_name: k=v` pattern; that
decision is restated below as Decision 6 with its rationale.

---

## Decision 1 — Where the new webhook view lives

**Decision**: New view `DirectSendCategoryWebhook` lives at
`retail/webhooks/templates/views/direct_send_category.py`, alongside
the existing `TemplatesStatusWebhook`
(`retail/webhooks/templates/views/template_status_update.py`). A new
URL entry in `retail/webhooks/templates/urls.py` exposes it at
`templates-status/api/category-notification/`.

**Rationale**:

- The spec's FR-001 mandates the new endpoint be reachable under the
  existing `retail.webhooks.templates` URL namespace so operators
  find both Direct Send-related template webhooks in one place.
- Co-location with `TemplatesStatusWebhook` matches the existing
  file-layout convention: each webhook has one `views/<name>.py` +
  one `usecases/<name>.py` pair, with the shared `serializers.py`
  carrying serializers for both.
- The URL prefix `templates-status/api/` is the existing convention
  (`retail/webhooks/templates/urls.py:10` uses
  `templates-status/api/notification/` for the status webhook); the
  new path `templates-status/api/category-notification/` reuses the
  prefix and disambiguates the sub-path. Both endpoints are mounted
  under the project-wide `/webhook/` prefix from
  `retail/webhooks/urls.py:6`.

**Alternatives considered**:

- *Place the new webhook under a new top-level app (e.g.
  `retail.webhooks.direct_send`)*: rejected because the spec's FR-001
  explicitly says "under the existing `retail.webhooks.templates`
  URL namespace". A new app would also force two new `__init__.py`
  files and a new entry in `retail/webhooks/urls.py`, with no
  discoverability benefit.
- *Reuse `TemplatesStatusWebhook` with a payload-driven dispatch
  switch*: rejected because the two webhooks have different payload
  shapes (status webhook takes `app_uuid + template_statuses` dict;
  category webhook takes 5 named fields), different response shapes,
  and different idempotency contracts. Bundling them would force a
  Liskov-violating internal branch and break the single-responsibility
  guarantee of each use case.

---

## Decision 2 — How `(project_uuid, app_uuid)` resolves to `IntegratedAgent`s

**Decision**: The IntegratedAgent queryset is

```python
IntegratedAgent.objects.filter(
    project__uuid=dto.project_uuid,
    templates__versions__integrations_app_uuid=dto.app_uuid,
).distinct()
```

The tenant scoping clause (`project__uuid == payload.project_uuid`)
is the SC-006 cross-tenant boundary; the `templates__versions__integrations_app_uuid`
clause is the "linked to this app" definition from the user's
description. `.distinct()` collapses the cartesian product so a
single IntegratedAgent with N Versions on the same `app_uuid` is
returned once.

**Rationale**:

- The `app_uuid` → IntegratedAgent linkage is materialized
  exclusively via `Version.integrations_app_uuid` (spec.md A4 / A5).
  There is no separate column on `IntegratedAgent` storing
  `app_uuid` — its `channel_uuid` is a different identifier (the
  WhatsApp channel UUID, not the WhatsApp Cloud app UUID). The
  `Version.integrations_app_uuid` column is populated at
  template-creation time by
  `retail.templates.usecases._base_template_creator._create_version`
  (`retail/templates/usecases/_base_template_creator.py:24-38`) and
  is therefore present on every IntegratedAgent that has at least
  one Template.
- Filtering through `templates__versions__integrations_app_uuid`
  exploits the existing FK chain
  `IntegratedAgent ← Template ← Version` with the reverse-accessor
  `templates` (declared on `Template.integrated_agent` at
  `retail/templates/models.py:23-29`) and the reverse-accessor
  `versions` (declared on `Version.template` at
  `retail/templates/models.py:61-63`). The Django ORM compiles this
  to a single SQL query with two INNER JOINs, scoped by
  `IntegratedAgent.project_id`.
- The `is_active=False` filter is explicitly NOT applied (FR-004a).
  An old IntegratedAgent whose templates were created against the
  same `app_uuid` still has those templates in the DB; an
  incorrect-category determination is a property of the template
  content, not of the IntegratedAgent's activation status.
  Filtering on `is_active=True` would silently desync historical
  templates and break the "FLAGGED is terminal-for-dispatch"
  guarantee from spec 002's FR-007 / FR-012.
- `.distinct()` is necessary because the JOIN through
  `templates__versions__integrations_app_uuid` produces one row per
  matching Version; without it, an IntegratedAgent with 4 OrderStatus
  templates (each with 1+ Versions for the same `app_uuid`) would
  appear 4+ times in the result set.

**Alternatives considered**:

- *Pre-filter Versions by `integrations_app_uuid` then walk back
  through `template.integrated_agent`*: rejected because it requires
  the use case to perform two queries (one for Versions, one for
  IntegratedAgents) and either (a) build the IntegratedAgent set in
  Python with a `{v.template.integrated_agent_id for v in versions}`
  comprehension (loses the queryset abstractions) or (b) issue a
  second `IntegratedAgent.objects.filter(id__in=...)` query. Either
  path is strictly worse than the JOIN-and-distinct approach.
- *Add a denormalized `IntegratedAgent.app_uuid` column*: rejected
  as schema churn for a webhook that fires at most a few times per
  hour in the steady state. The JOIN cost is bounded by the
  cardinality of `Template`/`Version` per IntegratedAgent (4 for the
  current OrderStatus fleet), so the query plan is trivially cheap
  on the production indexes.

---

## Decision 3 — Cross-tenant isolation guarantee

**Decision**: Cross-tenant isolation is enforced at the SQL level
by the `project__uuid=dto.project_uuid` clause in the queryset
described in Decision 2. An IntegratedAgent in project B whose
Versions happen to carry the same `app_uuid` as the payload is
EXCLUDED because the IntegratedAgent's `project_id` does not equal
the payload's `project_uuid`. The audit log records
`no_matching_integrated_agent` for the named project without
emitting any reference to the IntegratedAgent in the other project
(FR-009d's enumeration of `no_matching_integrated_agent` carries
ONLY the five payload values; it does NOT include any
IntegratedAgent / Template / Version identifiers because none were
resolved within the named tenant).

**Rationale**:

- Spec.md SC-006 is the explicit measurable outcome: "in zero cases
  does a webhook for project A flag a template owned by project B,
  even when the `app_uuid` value coincidentally appears on a
  Version row in project B".
- The single-clause SQL-level boundary is structurally enforced (a
  developer who removes the `project__uuid=...` clause breaks the
  cross-tenant test added in tasks.md), versus a Python-level guard
  that would have to be inspected for correctness.
- The audit-log enumeration in FR-009d is the second layer of the
  isolation guarantee: even on a misrouted event, the audit log
  cannot leak references to the other tenant's data because no
  identifier from the other tenant ever enters scope.

**Alternatives considered**:

- *Add a Django middleware / queryset wrapper that asserts tenant
  scoping at every read*: rejected for v1 (same reasoning as spec
  002's FR-040 acceptance — "the audit query + the FK constraints
  + code review are the merge gate"). The webhook's surface is
  small enough (one queryset) that a single test + the code review
  is sufficient.
- *Use `Project.id` (integer FK) instead of `Project.uuid`*:
  rejected because the payload carries `project_uuid` (a UUID) and
  the lookup must consult `Project.uuid` (which has `unique=True`
  at `retail/projects/models.py:16`). Converting to `Project.id`
  in Python would force an extra lookup query.

---

## Decision 4 — Template lookup per IntegratedAgent

**Decision**: For each matched IntegratedAgent, the template lookup is

```python
template = (
    integrated_agent.templates
    .select_related("current_version")
    .filter(name=dto.template_name)
    .first()
)
```

The `name` comparison is case-sensitive (DB-native string equality),
the `is_active` filter is explicitly NOT applied (the IntegratedAgent
itself may be `is_active=False` per Decision 2's FR-004a, and the
Template's own `is_active` flag is a soft-delete marker that does
not affect the category-correctness determination), and
`select_related("current_version")` eager-loads the Version row so
the flagging-condition evaluation and the status read happen without
an extra query.

**Rationale**:

- FR-005 mandates exact-match, case-sensitive lookup of
  `Template.name`. The OrderStatus fleet's template names are
  lowercase snake_case per spec.md A8, so casing collisions are
  operationally improbable; the conservative case-sensitive lookup
  matches the upstream contract (Integrations is the contracting
  party for the casing of `template_name`).
- Using the IntegratedAgent's `templates` reverse-accessor
  (declared at `retail/templates/models.py:23-29`) is the canonical
  way to scope the Template lookup to the matched IntegratedAgent.
  Filtering by `integrated_agent_id` directly would be equivalent
  but less idiomatic.
- `select_related("current_version")` is a single INNER JOIN — the
  alternative (`prefetch_related`) is wrong for a OneToOne
  relationship and would issue two queries instead of one.
  `current_version` is a OneToOne FK declared at
  `retail/templates/models.py:15-21` with `on_delete=SET_NULL`, so
  the `current_version__isnull=True` case (the
  `template_has_no_current_version` event per FR-005a) is handled
  by the Python-side `if template.current_version is None` guard.

**Alternatives considered**:

- *Use `integrated_agent.templates.get(name=...)`*: rejected because
  `get()` raises `DoesNotExist` on the no-row case (FR-005's silent
  skip + `template_not_found` audit log), which would force an
  exception-handling clause in the use case. The `.first()` form
  returns `None` deterministically and routes through the
  `if template is None: emit template_not_found; continue` branch
  more cleanly.
- *Skip `select_related` and rely on the lazy `current_version`
  read*: rejected because the lazy read would fire one extra query
  per matched Template; for the multi-IntegratedAgent fan-out case
  (US1 scenario 4) the query count would grow linearly with the
  fan-out cardinality.

---

## Decision 5 — Idempotency without a dedup cache

**Decision**: Idempotency is achieved purely by the early-return
guard inside the use case:

```python
if template.current_version.status == "FLAGGED":
    if flagging_condition_fires:
        self._emit_flag_replay_noop(...)
    else:
        self._emit_no_action_required_already_flagged(...)
    return  # no UPDATE
```

No dedup cache (Redis SETNX or LocMemCache wrapper) is introduced
for this webhook.

**Rationale**:

- FR-007c / FR-008 / FR-008a are explicit: the early-return guard
  is the sole idempotency mechanism. The webhook is the producer of
  `FLAGGED`-state writes, and the underlying write is a single-row
  `UPDATE` against `Version.status` — concurrency is handled by
  Postgres' implicit row-level UPDATE lock under Django's default
  per-statement transaction model (READ COMMITTED isolation does
  not by itself serialize transactions, but the per-row exclusive
  lock taken by `UPDATE` is sufficient for this single-column
  write); both concurrent calls converge on the same final state
  without application-level coordination.
- A dedup cache would have to be invalidated when the operator
  later restores the template to `APPROVED` via
  `UpdateTemplateUseCase` (FR-014's recovery channel). Without the
  invalidation, the cache would treat a legitimate re-flagging
  after restoration as a replay and silently skip the UPDATE. The
  invalidation hook would have to live in `UpdateTemplateUseCase`
  (cross-app coupling) or in a Django signal on `Version.save`
  (broad blast radius). Both designs are strictly worse than the
  early-return guard, which reads the actual current state every
  time.
- Spec 002's order-status broadcast dedup (FR-028 — keyed by
  `(project, agent, order, state)`) is unrelated: it dedups
  *broadcasts*, not *category-detection events*, and the cache key
  shape, dedup window, and failure mode are different. Reusing
  the cache backend with a different key shape would conflate two
  unrelated invariants.

**Alternatives considered**:

- *Use `cache.add(...)` with the canonical tuple
  `(project_uuid, app_uuid, template_name)` as key*: rejected for
  the invalidation reason above. Also rejected on the "dedup-cache
  failure mode" axis — the order-status dedup fails CLOSED (a
  cache outage means the broadcast is refused; spec 002's FR-028),
  which is acceptable because the upstream courier retries. For a
  category-detection event, fail-closed on a cache outage would
  let an incorrect-category template keep dispatching while the
  cache is unreachable; fail-open would re-flag and re-write on
  every retry. Neither failure mode is better than the early-return
  guard, which has no cache dependency at all.
- *Use `Version.objects.filter(...).update(status="FLAGGED")`
  unconditionally* (no early-return — let Postgres do the no-op
  write): rejected because the audit log would lose the
  `flag_replay_noop` / `no_action_required_already_flagged`
  distinction (every call would log `flagged`), and operators would
  have no way to distinguish a real state transition from a replay.

---

## Decision 6 — Audit log shape (Pattern B)

**Decision**: Every log line emitted by the webhook follows the
`[DirectSendCategoryWebhook] <event_name>: <k=v> ...` shape — the
same `[TAG] event_name: k=v` pattern used by `[CART_SERVICE]`
(`retail/webhooks/vtex/services_cart_abandonment_unified.py`),
`[ORDER_STATUS]` / `[CONVERSION_TRACKING]` (`retail/vtex/tasks.py:113-177`),
and spec 002's `[BroadcastDispatch]` / `[DirectSend]` /
`[AssignAgent]` audit trails. The legacy
`TemplatesStatusWebhook`'s unprefixed free-form format
(`retail/webhooks/templates/usecases/template_status_update.py:32-58`)
is NOT used by this webhook.

This decision was pinned by the Clarifications session 2026-05-24
(spec.md §Clarifications Q1; FR-009 / FR-009a–e).

**Rationale**:

- The `[TAG] event_name: k=v` pattern is the convention used by
  every webhook / task added in 2026 (spec 002 + `[CART_SERVICE]` +
  `[ORDER_STATUS]` + `[CONVERSION_TRACKING]`). Operators have built
  dashboards that filter on `[TAG]` as the routing token; adopting
  the same shape extends those dashboards trivially.
- The closed enumeration of `event_name` tokens in FR-009a is the
  contract surface for operator dashboards — it ensures dashboards
  can route on each operation outcome independently without
  parsing the free-form message body.
- Log-level discipline (INFO / WARNING / ERROR) mirrors
  `[ORDER_STATUS]` (`retail/vtex/tasks.py:166-177`): INFO for the
  happy path and replays, WARNING for "expected but unhappy"
  lookup misses, ERROR with `exc_info=True` for `unexpected_error`
  only. This is the discipline operators expect from the existing
  2026-era audit-log surface.
- The `reason=<sub_reason>` k=v on `flagged` events (closed
  enumeration `{category_mismatch, category_not_utility,
  category_mismatch_and_not_utility}` per FR-006b / FR-009a) gives
  operator dashboards a single-token filter for "why was this
  flagged" without parsing the category values.

**Alternatives considered**:

- *Use the legacy `TemplatesStatusWebhook`'s unprefixed free-form
  format*: rejected by the Clarifications session. Free-form
  messages are harder to filter in Kibana/CloudWatch, and the
  legacy format does not carry the structured `event_name`
  discriminator that operator dashboards require.
- *Use structured logging (JSON via `python-json-logger`)*:
  rejected because the rest of the codebase emits f-string text
  logs; introducing JSON for one webhook would force the
  log-shipping pipeline to handle two formats. JSON could be a
  follow-up if a broader codebase migration happens, but it is
  out of scope for this feature.

---

## Decision 7 — No Service / Client layer is introduced

**Decision**: This feature introduces no new Service class and no
new Client class. The use case performs only ORM operations
(Postgres reads and one `UPDATE` per matched Template); there is no
outbound HTTP, no MCP call, no cache touch, no broker publish, no
S3 / Lambda invocation.

**Rationale**:

- Constitution Principle I scopes the Service layer to "thin
  wrappers around clients that handle infrastructure exceptions"
  and the Client layer to "the only layer allowed to perform
  outbound HTTP calls". A webhook that only reads and writes
  Postgres has no such surface — introducing an empty Service /
  Client pair would be cargo-culted architecture.
- Spec 002's
  `MetaService.fetch_library_template_by_name_and_language` is the
  precedent for "introduce a Service when adding outbound HTTP";
  the inverse precedent ("do not introduce a Service for pure-ORM
  use cases") is followed by every existing use case under
  `retail/webhooks/templates/usecases/` and
  `retail/templates/usecases/`.
- The ORM is the "infrastructure" boundary for this use case, and
  the framework (Django) already wraps OperationalError /
  IntegrityError / DatabaseError via the same exception hierarchy
  the use case's `try / except Exception as exc` block catches
  (FR-010b — HTTP 500 only for genuinely unexpected exceptions).

**Alternatives considered**:

- *Wrap the ORM queries in a `TemplateStatusService`*: rejected as
  premature abstraction (YAGNI). A future feature that needs to
  share the lookup logic with another caller could extract a Service
  at that time; for the current single-call surface, the use case
  owns the queries directly.

---

## Decision 8 — Per-request transaction boundary

**Decision**: The use case does NOT wrap its work in an explicit
`@transaction.atomic` block. Each matched IntegratedAgent's Template
update is a single-row `UPDATE` against `Version.status`; the N
updates across N matched IntegratedAgents are intentionally
best-effort sequential — one IntegratedAgent's failure (e.g. an
`IntegrityError` from a concurrent migration) does NOT roll back
the others.

**Rationale**:

- FR-007b is explicit: "No transaction wrapping is required because
  the update is a single-row write per Template; the iteration
  across multiple matched IntegratedAgents is best-effort sequential
  and does not require atomicity (one IntegratedAgent's success is
  independent of another's failure)."
- The single-row `UPDATE` is itself atomic (Postgres MVCC
  guarantees it); transaction wrapping would only matter if the use
  case wrote multiple rows that needed to be committed together.
  In the multi-IntegratedAgent fan-out case (US1 scenario 4), each
  IntegratedAgent's row is logically independent — there is no
  cross-IntegratedAgent invariant to preserve.
- Spec 002's `AssignAgentUseCase` is `@transaction.atomic` because
  it persists ~10 related rows (IntegratedAgent + Credentials +
  Templates + Versions) that must be committed together. This
  webhook's surface is the opposite: ~1 row updated per
  IntegratedAgent, with no cross-row dependencies.
- The caught-exception path (FR-010b) returns HTTP 500 if a single
  IntegratedAgent's UPDATE raises. The upstream courier's retry
  will re-fire the same payload; on retry, the IntegratedAgents
  that succeeded the first time observe `FLAGGED` already and
  emit `flag_replay_noop` (no UPDATE), while the ones that failed
  the first time get a fresh shot. This is the right
  retry-convergence behavior for the webhook's idempotency
  contract.

**Alternatives considered**:

- *Wrap the whole fan-out in `@transaction.atomic`*: rejected
  because a single IntegratedAgent's failure would roll back the
  others' UPDATEs, forcing the upstream courier to retry the entire
  batch (including the already-succeeded IntegratedAgents) until
  every member of the fan-out succeeds. For the multi-agent fan-out
  case (US1 scenario 4), this would amplify a transient DB issue
  on one IntegratedAgent into a retry storm across the entire
  fleet.
- *Wrap each per-IntegratedAgent update in a savepoint
  (`@transaction.atomic` inside the loop)*: rejected as overkill —
  the single-row UPDATE is already atomic at the SQL level, so the
  savepoint adds nothing but overhead.

---

## Decision 9 — Use case input is a frozen DTO

**Decision**: The view passes a `DirectSendCategoryDTO`
(`@dataclass(frozen=True)`) to the use case's `execute(...)` method.
The DTO carries the five validated payload fields:

```python
@dataclass(frozen=True)
class DirectSendCategoryDTO:
    project_uuid: UUID
    app_uuid: UUID
    template_name: str
    template_category: str
    template_correct_category: str
```

**Rationale**:

- Constitution Principle I's view-layer rule mandates "build a frozen
  DTO" between serializer validation and use-case delegation. The
  DTO carries the immutable contract surface for the use case and
  prevents downstream mutation of validated input.
- Five fields is just enough to warrant a DTO; ad-hoc keyword
  arguments (`execute(project_uuid=..., app_uuid=..., ...)`) would
  force every test to spell out the parameter list and would lose
  the immutability guarantee.
- Spec 002's `UpdateTemplateData` (`TypedDict`) is a precedent for
  passing structured input to a use case, but `TypedDict` does not
  enforce frozenness at runtime. A `@dataclass(frozen=True)` is the
  modern Python idiom for this purpose and is used by spec 002's
  `OrderStatusDTO` (`retail/vtex/tasks.py:5-19` — `OrderStatusDTO`
  is declared in `retail/vtex/usecases/order_status.py`).

**Alternatives considered**:

- *Pass the DRF `validated_data` dict directly to the use case*:
  rejected — DRF dicts carry mutable references and lose type
  information; passing them into the use case ties the use case to
  the DRF serializer shape and breaks Principle I's "framework-agnostic
  use case" rule.
- *Use a `TypedDict`*: rejected because `TypedDict` is structurally
  typed and does not provide runtime immutability. A `dataclass(frozen=True)`
  gives both type information and immutability for free.

---

## Decision 10 — Use case returns a result DTO with `to_dict()`

**Decision**: The use case's `execute(...)` method returns a
`DirectSendCategoryResult` dataclass with three fields:

```python
@dataclass(frozen=True)
class DirectSendCategoryResult:
    templates_updated: int
    integrated_agents_inspected: int
    detail: str

    def to_dict(self) -> dict:
        return {
            "detail": self.detail,
            "templates_updated": self.templates_updated,
            "integrated_agents_inspected": self.integrated_agents_inspected,
        }
```

The view then shapes the HTTP response as
`Response(result.to_dict(), status=200)`.

**Rationale**:

- Constitution Principle I's use-case-result rule mandates "Returns
  a result dataclass with a `to_dict()` method when the view needs
  structured output". This pattern keeps the use case
  framework-agnostic (it returns a Python value, not a DRF
  Response) while giving the view a single delegation point for
  the HTTP shape.
- FR-010 fixes the response shape at
  `{detail, templates_updated, integrated_agents_inspected}`. The
  result DTO mirrors that shape one-to-one so the view's mapping is
  trivial (no field renaming, no nested object construction).
- The same counters (`templates_updated`,
  `integrated_agents_inspected`) appear on the FR-009c `completed`
  log line and the HTTP 200 response body. The use case computes
  them once and emits them via both the audit log and the result
  DTO — there is no duplication.

**Alternatives considered**:

- *Return a `dict` directly*: rejected — loses type information and
  invites callers to introduce ad-hoc keys ("how many extra fields
  should I return?"). The frozen dataclass pins the shape.
- *Return a `TypedDict`*: rejected for the same reason as Decision
  9 (no runtime immutability).
- *Return the response counters as a tuple
  `(templates_updated, integrated_agents_inspected, detail)`*:
  rejected — positional tuples make the view layer's mapping
  fragile (a future re-order of the tuple silently swaps fields).

---

## Decision 11 — Test layout and coverage strategy

**Decision**: Three new test files land in this PR:

- `retail/webhooks/templates/tests/usecases/test_direct_send_category.py`
  — unit tests for `DirectSendCategoryWebhookUseCase` (every branch
  of the FR-006 flagging condition, every event name from FR-009a,
  the multi-IntegratedAgent fan-out from US1 scenario 4, the
  cross-tenant exclusion from Decision 3, the idempotency
  early-return from Decision 5).
- `retail/webhooks/templates/tests/views/test_direct_send_category.py`
  — view-level HTTP tests (200 / 400 / 401 / 500 boundary,
  authentication via `BaseTestMixin.setup_internal_user_permissions`).
- An integration test (`tasks.md` T019) lands in the same
  `tests/views/` file as a separate test class; it exercises the
  end-to-end "webhook fires → `FLAGGED` written → next dispatch
  attempt skipped by spec 002's gate" path.

A new `__init__.py` is created at
`retail/webhooks/templates/tests/__init__.py` (and at the two
`tests/usecases/` and `tests/views/` sub-folders) because the
existing webhook has no tests today (Complexity Tracking row 1 in
plan.md).

**Rationale**:

- Constitution Principle III's "Every PR MUST sustain or raise the
  project coverage" rule is satisfied by the three test files;
  every new code branch is exercised. The use case's flagging
  condition has 4 cells in its truth table (4 combinations of
  match × is-UTILITY); the use case's outcome tree has 10 event
  names; the view has 4 HTTP outcomes. The test surface is finite
  and exhaustively covered.
- The view tests use `BaseTestMixin` for the
  `setup_internal_user_permissions` helper, mirroring spec 002's
  view tests
  (`retail/agents/tests/views/test_assign_agent_view.py` and similar).
- The integration test verifies that the dispatch gate from spec
  002 (`Broadcast.get_current_template`) actually skips the
  broadcast when this webhook flips the Version to `FLAGGED`. This
  is the only point in the test surface where the two specs touch;
  the integration test is the gate that catches a future change to
  the dispatch-gate code that would break the FLAGGED contract
  (FR-013).

**Alternatives considered**:

- *Backfill tests for the legacy `TemplatesStatusWebhook` in the
  same PR*: rejected for the reasons in plan.md's Complexity
  Tracking row 1 (PR-surface conflation, ambiguous coverage
  reporting). Captured as a follow-up PR
  `test/templates-status-webhook-tests`.
- *Skip the integration test*: rejected — FR-013 names the
  dispatch gate as an external dependency, and the spec's SC-002
  ("After a template is flagged by this webhook, the next
  broadcast attempt against that template is skipped 100% of the
  time") is a behavioral guarantee that crosses two apps. Without
  the integration test, a future PR could break SC-002 silently.

---

## Decisions explicitly NOT taken (out of scope)

Captured for completeness so reviewers see what was considered and
rejected for v1. Each item is a follow-up candidate scoped to its
own PR.

- **Email notification (`N → O` in `docs/direct_send-2026-05-20-201859.mmd`)**:
  FR-011 — out of scope. The audit log lines from FR-009 are the
  v1 operator observability surface. A follow-up feature MAY add
  email if operational data shows the audit log alone is
  insufficient.
- **`direct_send=true` upstream filter on the courier/Integrations
  side** (`P` in the diagram): FR-012 — out of scope. This webhook
  trusts the upstream to send only events relevant to Retail.
- **Dispatch-gate logic in
  `Broadcast.get_current_template`**: FR-013 — out of scope.
  Already implemented by spec 002.
- **Automated `FLAGGED → APPROVED` demote**: FR-014 — out of scope.
  Operator-driven recovery via `UpdateTemplateUseCase` remains the
  only supported channel until / unless a future feature
  introduces an automated demote webhook.
- **A new dedup cache for this webhook**: rejected by Decision 5 —
  the early-return guard is the v1 idempotency mechanism.
- **A new database migration**: rejected by spec.md A10 — the
  `FLAGGED` enum value already exists.
- **A new env var or settings key**: rejected by plan.md's
  Constraints section — the webhook reuses `CanCommunicateInternally`'s
  existing auth configuration.
- **A new service / client layer**: rejected by Decision 7 — the
  use case performs only ORM operations.
- **An explicit transaction boundary across the
  multi-IntegratedAgent fan-out**: rejected by Decision 8 —
  best-effort sequential is the right convergence behavior.
- **Structured JSON logging**: rejected by Decision 6 — out of
  scope for this feature.
- **Backfill tests for the legacy `TemplatesStatusWebhook`**:
  rejected by Decision 11 — captured as a follow-up PR.
