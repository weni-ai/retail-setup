# Phase 1 Data Model: WhatsApp Direct Send Broadcasts (OrderStatus)

**Feature**: `002-direct-send-broadcasts`
**Date**: 2026-05-20
**Spec**: `./spec.md`
**Research**: `./research.md`

This document captures the persisted-state changes required by the
feature. New rows / new columns / new enum values are listed with
their owning model, validation rules, and the migration approach.
Pure in-memory DTOs are listed at the end for completeness.

---

## 1. `IntegratedAgent` — add `direct_send` flag

**File**: `retail/agents/domains/agent_integration/models.py`

### New field

| Name          | Type            | Default | Null  | Notes                                                          |
| ------------- | --------------- | ------- | ----- | -------------------------------------------------------------- |
| `direct_send` | `BooleanField`  | `False` | False | Snapshot of the WhatsApp channel's Direct Send flag at the time the agent is assigned. Determines which dispatch path applies for every broadcast originated by this IntegratedAgent (FR-001). |

### Validation rules

- Set exclusively by `AssignAgentUseCase` at assignment time (FR-002).
- Once set, the flag is immutable for the lifetime of the IntegratedAgent
  (FR-002 Assumption: "snapshot at assignment time"). Re-assignment
  is the only path that changes it.

### Migration

A single Django migration:

- `AddField IntegratedAgent.direct_send (BooleanField, default=False)`.
- Default `False` is enough for both new rows and the backfill of
  existing rows (Decision 13). No `RunPython` step required.

### Reverse-relations affected

None. The new field is a scalar boolean and does not introduce a
relation.

---

## 2. `Version` status enum — add `PAUSED` and `FLAGGED`

**File**: `retail/templates/models.py`

### Updated enum

```python
STATUS_CHOICES = (
    ("APPROVED", "Approved"),
    ("IN_APPEAL", "In Appeal"),
    ("PENDING", "Pending"),
    ("REJECTED", "Rejected"),
    ("PENDING_DELETION", "Pending Deletion"),
    ("DELETED", "Deleted"),
    ("DISABLED", "Disabled"),
    ("LOCKED", "Locked"),
    ("PAUSED", "Paused"),    # NEW (FR-006)
    ("FLAGGED", "Flagged"),  # NEW (FR-006)
)
```

### Validation rules

- `PAUSED` and `FLAGGED` are broadcast-disabling statuses (FR-007).
- The mechanism that transitions a Version into `PAUSED` / `FLAGGED`
  is **out of scope** for this feature (FR-009). Persistence and
  dispatch-time behavior of the values are the only contract this
  spec adds.

### Migration

A single `AlterField` migration that replaces the old `choices`
tuple with the extended one. No data migration is required because
existing rows already store one of the legacy values.

### Type-aliases that must update in lockstep

- `retail/templates/usecases/update_template.py`
  → `class UpdateTemplateData(TypedDict).status: Literal[...]` —
  extend the `Literal` with `"PAUSED"` and `"FLAGGED"` so callers
  can update Versions to the new states once the upstream feature
  introduces the transition mechanism.

### Read sites that gain new behavior

| Site                                                                                                                | Today                                                                                                            | After the change                                                                                                                          |
| ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `Broadcast.get_current_template` at `retail/agents/domains/agent_webhook/services/broadcast.py:602`                  | Filters `current_version__status="APPROVED"`. Non-APPROVED versions silently produce a "template not found" log. | Same filter. New audit-log entry when the version's status is `PAUSED` or `FLAGGED`, identifying the template, the version status, and the originating order-status event (FR-012). |
| `SendTestTemplateUseCase._get_active_template` at `retail/api/integrated_agent/usecases/send_test_template.py:50`     | Same filter; raises `ValidationError` on miss.                                                                   | Same filter. The error message includes `PAUSED`/`FLAGGED` reasons when applicable so internal QA users have a clear cause.               |
| `PushAgentUseCase.has_delivered_order_templates_by_integrated_agent` at `retail/agents/domains/agent_management/usecases/push.py:214` | `status="APPROVED"`.                                                                                             | No change. `PAUSED`/`FLAGGED` correctly return `False` for "has integrated delivered-order templates" — same as REJECTED today.            |

---

## 3. `Template` — no schema change, only a new metadata key contract

**File**: `retail/templates/models.py`

### `Template.metadata` shape — Direct Send-enabled assignments

The `metadata` JSONField already stores the result of the
library-catalog adapter (`TemplateTranslationAdapter`) in the shape
produced by `ValidatePreApprovedTemplatesUseCase._get_template_info`.
For Direct Send-enabled assignments, the same shape is persisted
verbatim, with one extra key:

```jsonc
{
  "header": { ... },
  "body": "Olá {{1}}, seu pedido {{2}} foi enviado.",
  "body_params": [ ... ],
  "footer": "Equipe Loja XYZ",
  "buttons": [ { "type": "URL", "text": "Acompanhar pedido", "url": "https://loja.com/track/{{1}}" } ],
  "category": "UTILITY",
  "language": "pt_BR",
  "direct_send": {                       // NEW key (only present when populated via the Direct Send path)
      "fetched_from_meta_library": true,
      "fetched_at": "2026-05-20T12:34:56Z",
      "requested_language": "es_MX",     // the project-resolved language requested before any fallback
      "actual_language": "pt_BR"         // always present; equals requested_language when FR-003c fallback did NOT fire,
                                         // and differs when the pt_BR fallback succeeded
  }
}
```

### Rationale

- A small, additive sub-object inside `metadata` records the
  library-catalog source of truth and the language fallback (if
  any). It is observability data only; the dispatch path does NOT
  branch on it.
- It is intentionally namespaced under `"direct_send"` so it cannot
  collide with the existing keys produced by `_get_template_info`.

### Validation rules

- The key is added only by the Direct Send-enabled assignment branch
  in `AssignAgentUseCase`. The legacy path leaves `metadata`
  untouched.
- No Django-level validation on the JSON. The schema is enforced by
  the use case that writes it.

---

## 4. `Version.status="APPROVED"` written at Direct Send assignment time

**File**: `retail/templates/models.py`

### Behavior change (no schema change)

When a Template is created through the Direct Send-enabled
assignment branch, its corresponding `Version` is persisted with
`status="APPROVED"` immediately (FR-004). This mirrors the existing
behavior of `_adopt_customer_templates`
(`retail/agents/domains/agent_integration/usecases/assign.py:315`),
which already writes `version.status = "APPROVED"` when adopting a
customer-side translation.

### Rationale

- The Direct Send path takes Meta's library-catalog template as
  authoritative; there is no asynchronous approval cycle. Status
  must reflect "ready to broadcast" the moment the row exists.
- We don't introduce a new "AUTO_APPROVED" or "DIRECT_SEND_APPROVED"
  status because the dispatch gate already keys exclusively on
  `APPROVED` (Decision 10) — adding a parallel "approved-equivalent"
  status would force the gate to use `status__in`, which is needless
  churn.

---

## 5. New in-memory DTOs / TypedDicts (not persisted)

The following DTOs are pure value objects used between the new use
cases and services. They live in the same files as the use cases
that own them (matching the project's existing convention).

### `DirectSendChannelStatus` — read of the WhatsApp channel's flag

```python
@dataclass(frozen=True)
class DirectSendChannelStatus:
    enabled: bool                            # Direct Send flag from the channel-app
    source: Literal["channel_app", "default_on_lookup_failure"]
```

- Built by a private helper inside `AssignAgentUseCase` from
  `IntegrationsService.get_channel_app(...)`.
- `source="default_on_lookup_failure"` → `enabled=False` AND a
  warning is logged (FR-005, Story 2 scenario 3).

### Library-catalog content adapter — reuses the existing `TemplateInfo`

Research Decision 9 splits the shared logic into two helpers in
`retail/templates/usecases/_meta_library_template_fetch.py`. Both
produce the **existing** `TemplateInfo` `TypedDict` already defined in
`retail/agents/domains/agent_management/usecases/validate_templates.py`:

```python
class TemplateInfo(TypedDict):
    name: str
    content: str
    metadata: Dict[str, Any]    # header, body, body_params, footer, buttons, category, language
```

- `adapt_meta_library_template_response(raw)` is the **pure adapter**
  shared between both paths — push-time validation flow
  (`ValidatePreApprovedTemplatesUseCase._get_template_info`) and the
  Direct Send-enabled assignment branch — so the local
  `Template.metadata` is built the same way on both paths
  (research Decision 9). Push-time keeps calling the legacy
  `meta_service.get_pre_approved_template(name, language)` (fuzzy
  semantics preserved per research Decision 4) and only delegates the
  response-shaping step to this adapter.
- `fetch_meta_library_template_metadata(meta_service, name, language)`
  is the **Direct-Send-only** HTTP wrapper. It calls
  `meta_service.fetch_library_template_by_name_and_language(name, language)`
  (exact-match) and delegates the response to the adapter above. Only
  the assignment use case's Direct Send branch uses it.
- The library-catalog response's `language` is already carried inside
  `TemplateInfo.metadata["language"]`; no separate top-level
  `language` field is needed on either helper's return type.

### Direct Send `actual_language` — derived in the assignment use case

The `actual_language` value that ends up in `Template.metadata.direct_send`
(see §3) is NOT a field of `TemplateInfo`. It is computed inside
`AssignAgentUseCase._create_library_templates` at write time, because
only the use case knows whether the `pt_BR` fallback fired:

```python
content = fetch_meta_library_template_metadata(meta_service, name, project_language)
actual_language = project_language

if content is None and project_language != "pt_BR":
    content = fetch_meta_library_template_metadata(meta_service, name, "pt_BR")
    if content is not None:
        actual_language = "pt_BR"
        logger.warning(f"[DirectSend] template_language_fallback: ...")

if content is None:
    raise DirectSendTemplateUnavailableError(...)

template.metadata = {
    **content["metadata"],
    "direct_send": {
        "fetched_from_meta_library": True,
        "fetched_at": now_utc_iso(),
        "requested_language": project_language,
        "actual_language":    actual_language,
    },
}
```

This keeps the helper pure (one input language, one return shape) and
puts the fallback orchestration where the transaction boundary lives.

### `DirectSendBroadcastPayload` — wire shape sent to the messaging gateway

The complete payload shape sent to the Flows broadcast endpoint is
specified in `./contracts/messaging-gateway-payload.md`. It is a
plain `Dict[str, Any]` at runtime (matching the existing
`Broadcast.build_broadcast_template_message` return type) so we
preserve the current calling convention.

### `DirectSendTemplateUnavailableError`, `DirectSendUnsupportedComponentError`

```python
from rest_framework.exceptions import APIException
from rest_framework import status

class DirectSendTemplateUnavailableError(APIException):
    """Raised at agent-assignment time when neither the project-resolved
    language nor the pt_BR fallback returns usable content for a
    required template (FR-003d).
    """
    status_code  = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "direct_send_template_unavailable"
    template_name: str
    requested_language: str
    fallback_language: str
    reason: str

class DirectSendUnsupportedComponentError(APIException):
    """Raised at agent-assignment time when Meta's library catalog
    returns a template whose components are outside the Direct Send
    supported set (Decision 12 — defensive).
    """
    status_code  = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "direct_send_unsupported_component"
    template_name: str
    component_type: str
```

- Both inherit from DRF's `APIException` so they are auto-translated
  to a 422 response by DRF's exception handler — no view-side
  try/except is required. The use case is `@transaction.atomic`, so
  all rows are rolled back automatically before the response is
  serialized. This matches the existing pattern for the sibling
  exceptions in `retail/agents/domains/agent_integration/exceptions.py`
  (`GlobalRuleUnprocessableEntity`, etc.).
- `default_code` is what DRF surfaces as the `code` key in the JSON
  response (alongside `detail`), so consumers can route on a stable
  identifier instead of parsing the human-readable message. The
  values pinned above match the `code` examples documented in
  `quickstart.md §7`.

---

## 6. State transitions

### `IntegratedAgent.direct_send`

```
                 ┌──────────────────────────────────────────┐
                 │ AssignAgentUseCase.execute               │
   ┌─────────┐   │   resolves channel.direct_send and       │
   │ <none>  │──►│   persists IntegratedAgent.direct_send   │
   └─────────┘   │   (atomic; never re-syncs after that)    │
                 └──────────────────────────────────────────┘
```

No transition out of the value other than re-assignment, which
deletes the old IntegratedAgent (or marks it `is_active=False`) and
creates a new one — same lifecycle the project has today.

### `Version.status` (new states only)

```
   ... existing states ...
   APPROVED ──────► PAUSED          (event-source: a future feature
   APPROVED ──────► FLAGGED          will write these transitions;
   PAUSED   ──────► APPROVED         this spec only persists the values
   FLAGGED  ──────► APPROVED         and exposes them at the dispatch gate)
```

Both `PAUSED` and `FLAGGED` are dispatch-disabling (Decision 10);
returning to `APPROVED` re-enables broadcasts on the next webhook
(FR-007 + Story 3 scenario 3 + SC-006).

---

## 7. Indexes and constraints

No new indexes or constraints are introduced.

- `IntegratedAgent.direct_send` does not justify an index — every
  read of the flag is keyed by the IntegratedAgent's PK or by
  `(project, agent)`; the boolean is effectively co-located.
- The status enum extension does not change any existing index. The
  dispatch gate already uses `current_version__status="APPROVED"`,
  which (per the existing migrations) is satisfied by the planner
  using the `current_version` FK column.

### 7.1 Tenant FK chain (canonical scoping)

Spec FR-040 requires that every read or write that touches
`IntegratedAgent`, `Credential`, `Template`, `Version`,
`BroadcastMessage`, `BroadcastConversion` be scoped through the
tenant FK chain documented in spec.md §Tenant isolation. The
canonical chain is:

```
BroadcastMessage      ──► project (FK to projects.Project)
                          retail/broadcasts/models.py:88-92

BroadcastConversion   ──► project (FK to projects.Project)
                          retail/broadcasts/models.py:236-240

IntegratedAgent       ──► project (FK to projects.Project)
                          retail/agents/domains/agent_integration/models.py:21-23

Credential            ──► integrated_agent ──► project (transitive)
                          retail/agents/domains/agent_integration/models.py:55-57

Agent                 ──► project (FK to projects.Project; Lambda namespace)
                          retail/agents/domains/agent_management/models.py:13-15

Template              ──► integrated_agent ──► project (transitive)
                          retail/templates/models.py:23-29

Version               ──► template ──► integrated_agent ──► project (transitive)
                                  AND
                      ──► project (FK to projects.Project, direct)
                          retail/templates/models.py:59-66
```

The dual-path scoping on `Version` (transitive via `template` AND
direct via `Version.project`) is intentional: `Version.project`
exists so the dispatch-time queryset at `Broadcast.get_current_template`
can filter by project without joining through `Template`. This
feature does NOT change either path; both are pre-existing FKs.

### 7.2 Referential-integrity invariants (FR-040, FR-045, FR-046, SC-010)

The following invariants MUST hold across the lifetime of the
schema. They are enforceable at the application layer (Django
write logic) and observable as SQL audit queries:

| # | Invariant                                                                          | Enforcement                                                                                  | Audit query / SC-010 reference                                                                                                                       |
| - | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `BroadcastMessage.project_id == BroadcastMessage.integrated_agent.project_id`      | Application — `RecordBroadcastSentUseCase` writes both FKs from the same `IntegratedAgent`.   | SC-010 (a). Audit query materialized in `tasks.md` T035c (two-project cross-tenant regression guard).                                                |
| 2 | `BroadcastConversion.project_id == BroadcastConversion.integrated_agent.project_id`| Application — `MarkBroadcastConvertedUseCase` writes both FKs from the matched `BroadcastMessage.project` and `last-touch broadcast.integrated_agent`. | SC-010 (b). Spot-checked by integration tests.                                                                                                       |
| 3 | `Template.integrated_agent.project_id == Version.project_id` for every (Template, Version) pair | Application — `_create_library_templates` and `_adopt_customer_templates` write both FKs from the same `IntegratedAgent`.   | SC-010 (c). Spot-checked by integration tests; FK constraints make the runtime violation a hard `IntegrityError`.                                    |
| 4 | `Version.integrations_app_uuid` corresponds to a channel app of the same project as `Version.project` | Application — assignment writes both fields from the SAME `app_uuid` query param + `Project-Uuid` header (FR-043 cross-validation). | Spec FR-043. v1 inherits Integrations-side authorization (see plan Constraints — Tenant isolation).                                                  |
| 5 | `Credential.integrated_agent.project_id` resolves to a single `Project` row        | Database — FK constraint on `Credential.integrated_agent` and on `IntegratedAgent.project`.   | SC-010 (d). FK-guaranteed.                                                                                                                           |
| 6 | `Template.name` and `Version.template_name` are NOT globally unique                | Database — neither column carries `unique=True`; the constraint was removed in `templates/0007_alter_template_name.py` and `templates/0015_alter_version_template_name.py`. | Spec FR-045. A future migration that re-introduces global `unique=True` on either column is a forbidden regression because Direct Send's per-WABA = per-IntegratedAgent uniqueness rule is the canonical scope. |
| 7 | `IntegratedAgent.channel_uuid` MAY appear at most once in the live `IntegratedAgent` set, modulo the upstream guarantee that Integrations Engine never issues the same channel UUID for two channels | Application — assignment writes `channel_uuid` from a query param whose project ownership is gated by FR-043 cross-validation. | Spec FR-043. The `IntegratedAgent.channel_uuid` column carries `null=True` but no `unique=True`; the per-project uniqueness is enforced at write time by the cross-validation. |

### 7.3 PAUSED / FLAGGED status checks are tenant-scoped (FR-046)

The dispatch-time skip for `PAUSED` and `FLAGGED` (FR-012, Decision
10) reads `Version.status` through the FK chain `Version → Template
→ IntegratedAgent → Project`. The lookup at
`Broadcast.get_current_template` is keyed on
`integrated_agent.templates.filter(name=...)`, which is the
per-IntegratedAgent reverse-relation; the project scoping is
transitive via `IntegratedAgent.project`. A future refactor that
performs a project-less status lookup (e.g. `Version.objects.filter(template_name=..., status="APPROVED")`
without a tenant join) is a forbidden regression because flipping
project A's `Version.status` would silently affect project B's
broadcasts. The dual-path scoping (item 7.1: `Version.project`
direct FK) gives a future implementer a project-scoped filter
that does NOT require a join back through `Template`.

### 7.4 `BroadcastConversion`'s tenant boundary

The `(project, order_id)` unique constraint on `BroadcastConversion`
(`broadcast_conversions_project_order_unique`,
`retail/broadcasts/models.py:271-275`) is the per-tenant boundary
for conversion attribution. A re-delivery of the `invoiced` event
for the same `(project, order_id)` collapses to the existing row
via `get_or_create` (FR-036) — the constraint is project-scoped,
so the same `order_id` value MAY legitimately appear in two
projects without colliding. The `MarkBroadcastConvertedUseCase`
last-touch attribution (FR-033) operates within the project scope
so no cross-tenant attribution is possible.

---

## 8. Backfill / data migration

None required. All changes are additive:

- `direct_send` defaults to `False` on existing rows (Decision 13).
- `PAUSED`/`FLAGGED` are unreachable on existing rows because no
  transition mechanism exists yet (FR-009).

---

## 9. Summary of file-level changes implied by this data model

| File                                                           | Change                                                                                                  |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `retail/agents/domains/agent_integration/models.py`            | Add `direct_send = BooleanField(default=False)` on `IntegratedAgent`.                                    |
| `retail/agents/migrations/00XX_integratedagent_direct_send.py` | Auto-generated `AddField` migration.                                                                    |
| `retail/templates/models.py`                                   | Extend `Version.STATUS_CHOICES` with `("PAUSED", "Paused")` and `("FLAGGED", "Flagged")`.                |
| `retail/templates/migrations/00XX_alter_version_status_paused_flagged.py` | Auto-generated `AlterField` migration.                                                                  |
| `retail/templates/usecases/update_template.py`                 | Extend `UpdateTemplateData.status` `Literal` with `"PAUSED"` and `"FLAGGED"`.                            |
| `retail/agents/domains/agent_integration/serializers.py`       | Expose `direct_send` (read-only) on `ReadIntegratedAgentSerializer`.                                     |

All other implementation surface (use cases, services, payload
builders, audit logging) is non-persisted code and is captured in
`./contracts/` and the implementation plan.
