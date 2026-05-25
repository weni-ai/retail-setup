# Phase 1 Data Model: Direct Send Template Incorrect-Category Webhook

**Feature**: `003-template-category-webhook`
**Date**: 2026-05-24
**Spec**: `./spec.md`
**Research**: `./research.md`

This document captures the persisted-state and in-memory data model
required by the feature. The feature has **zero schema changes** —
no new model, no new column, no new index, no new constraint, no
new migration. The only persisted-state change at runtime is a
single-row `UPDATE` against the existing `templates_version.status`
column.

The bulk of this document describes (a) the read interaction with
the three existing models the feature consults
(`Project`, `IntegratedAgent`, `Template`, `Version`), (b) the
single write site, and (c) the four in-memory DTOs (one inbound
DTO, one result DTO, and two private helper enums).

---

## 1. `Version.status` — bidirectional single-row UPDATE

**File**: `retail/templates/models.py` (read-only context — no
schema change ships against this model).

### Schema change

**None.** Both target values (`FLAGGED` and `APPROVED`) are already
members of `Version.STATUS_CHOICES` (`retail/templates/models.py:48-59`;
`FLAGGED` was added by spec 002's migration
`templates.0017_alter_version_status_paused_flagged`, `APPROVED` is
the long-standing default). This feature adds no value to the enum,
adds no field to the model, and adds no index / constraint to the
table.

### Write sites

There are exactly two write sites for this feature, both inside the
use case `DirectSendCategoryWebhookUseCase` (see `plan.md` §Source
Code):

```python
# (a) DirectSendCategoryWebhookUseCase._flag_version
#     — fires on the flag branch (FR-007).
version.status = "FLAGGED"
version.save(update_fields=["status"])

# (b) DirectSendCategoryWebhookUseCase._demote_version
#     — fires on the auto-demote branch (FR-006c / FR-007d).
version.status = "APPROVED"
version.save(update_fields=["status"])
```

Both call sites share the same mechanics (single-column write,
`update_fields=["status"]` mandatory, no `@transaction.atomic` wrap)
and differ only in the target value and the audit-log event name
(`flagged` vs `auto_demoted`).

- **Flag branch pre-condition**: `version.status != "FLAGGED"`
  AND the FR-006 flagging condition is true. The early-return guard
  for `version.status == "FLAGGED"` routes to the auto-demote
  dispatcher (clause below) instead of re-issuing the UPDATE.
- **Auto-demote branch pre-condition**: `version.status == "FLAGGED"`
  AND the FR-006 flagging condition is **false** (corrected-category
  signal — `template_correct_category == "UTILITY"`, regardless of
  `template_category`; pinned by Clarifications session 2026-05-25
  Q3). This is the symmetric inverse of the flag pre-condition (both
  rules are governed by the same single field — `template_correct_category`
  — making them exact inverses), and is the only path by which this
  webhook writes a non-`"FLAGGED"` status value.
- **Write post-conditions**:
  - Flag branch: `templates_version.status = 'FLAGGED'` on exactly
    one row.
  - Auto-demote branch: `templates_version.status = 'APPROVED'` on
    exactly one row.
- **Transaction boundary**: implicit per-statement transaction
  (Django default). No `@transaction.atomic` block wraps the use
  case (Decision 8). The multi-IntegratedAgent fan-out (US1
  scenario 4) issues N independent UPDATEs in sequence; one
  IntegratedAgent's failure does not roll back the others.
  Heterogeneous fan-outs (e.g. one IA flagged + one IA demoted in
  the same request) issue the two writes against two independent
  rows — no cross-row invariant to preserve.
- **Row identification**: the Version row is identified via
  `template.current_version` after the Template is matched by
  `(integrated_agent, name)`. The use case never queries `Version`
  directly by primary key; it always navigates through the
  Template's `current_version` OneToOne FK
  (`retail/templates/models.py:15-21`).
- **Update scope**: `update_fields=["status"]` is mandatory on
  both branches — the intent is "transition status, nothing else".
  Omitting `update_fields` would force Django to compare all 7
  columns on the Version row against the in-memory snapshot, which
  is wasted work and risks accidentally writing a stale field if
  another transaction modified the row between the read and the
  save (the one-second window between
  `template = .select_related(...).first()` and `version.save()`).
- **`current_version` pointer**: NEITHER write changes the
  Template's `current_version` FK (FR-007a is explicit on the flag
  branch and applies symmetrically to the demote branch — see
  spec.md FR-007d last sentence).
- **Side effects**: none. No Django signal fires on `Version.save`
  in the current codebase (verified by `Grep` on `post_save.*Version`
  / `pre_save.*Version` — returns zero hits inside the
  `retail.templates` app). The Project's `clear_integrated_agents_cache`
  signal (`retail/projects/models.py:43-51`) does not fire on
  Version updates.

### Read sites

The use case reads Version rows transitively via:

1. `template.current_version.status` (after the Template is matched
   by `(integrated_agent, name)`). This is the value evaluated by
   the flagging condition (FR-006) and the early-return guard
   (FR-007c). The `select_related("current_version")` eager-load
   means the Version row is loaded in the same query as the Template
   (Decision 4).
2. `template.current_version.uuid` — emitted on the audit log line
   as `version_uuid={...}` per FR-009d.
3. The IntegratedAgent fan-out queryset
   (Decision 2) walks `templates__versions__integrations_app_uuid`
   to match the payload's `app_uuid`. This reads the
   `integrations_app_uuid` column but never the `status` column on
   non-current Versions.

### Untouched columns

Of the seven columns on `Version` (`template`, `template_name`,
`integrations_app_uuid`, `project`, `status`, `created_at`, `uuid`),
this feature **only writes** `status`. The other six are read-only
context. FR-007a is explicit: "The update MUST NOT change the
Template's `current_version` pointer (the Template still points at
the same Version row; only the status string is updated)."

---

## 2. `IntegratedAgent` — fan-out queryset, no writes

**File**: `retail/agents/domains/agent_integration/models.py`
(read-only context — no schema change ships against this model).

### Schema change

**None.** The model is untouched. No field is added, no field is
removed, no field is renamed.

### Read sites

The use case issues one queryset against `IntegratedAgent`:

```python
# DirectSendCategoryWebhookUseCase._lookup_integrated_agents (illustrative)
IntegratedAgent.objects.filter(
    project__uuid=dto.project_uuid,
    templates__versions__integrations_app_uuid=dto.app_uuid,
).distinct()
```

- **Tenant scoping clause**: `project__uuid == dto.project_uuid`
  (Decision 3 — the SC-006 cross-tenant boundary). This is the
  single SQL-level clause that prevents flagging a template in
  project B for a webhook addressed to project A.
- **App-linkage clause**: `templates__versions__integrations_app_uuid == dto.app_uuid`
  (Decision 2 — the canonical interpretation of "IntegratedAgents
  linked to this app"). The JOIN walks the
  `IntegratedAgent.templates` reverse-accessor
  (`retail/templates/models.py:23-29`) and the
  `Template.versions` reverse-accessor
  (`retail/templates/models.py:61-63`).
- **`.distinct()`**: necessary because the JOIN produces one row
  per matching Version; without it, an IntegratedAgent with N
  Versions on the same `app_uuid` appears N times.
- **No `is_active=True` filter**: FR-004a explicitly mandates that
  inactive IntegratedAgents are included in the fan-out. The
  rationale is restated in Decision 2.
- **No `select_related`**: each matched IntegratedAgent's
  `project` and `templates` relationships are accessed via
  separate queries inside the loop body; eager-loading them at the
  fan-out level would be wasted work (the typical fan-out is 1
  IntegratedAgent, so the lazy load is fine).

### Write sites

**None.** The use case never writes to the `IntegratedAgent` model.
The `is_active` flag, the `ignore_templates` array, the
`broadcasts_delivered` counter — all read-only context.

### Untouched columns

All 13 columns on `IntegratedAgent` (`uuid`, `channel_uuid`,
`agent`, `project`, `is_active`, `ignore_templates`,
`contact_percentage`, `config`, `global_rule_code`,
`global_rule_prompt`, `parent_agent_uuid`, `created_on`,
`broadcasts_delivered`). The `uuid` field has `primary_key=True`
(legacy pattern), so Django adds no implicit `id` column on this
model; the in-source TODO comment at
`retail/agents/domains/agent_integration/models.py:8-15` captures
the migration path to a future integer PK plus separate `uuid`
field. The `config["direct_send"]` key introduced by spec 002 is
NOT consulted (the webhook trusts the upstream to send only
Direct Send-relevant events per FR-012; the dispatch-time gate
already differentiates Direct Send vs. legacy paths).

---

## 3. `Template` — name-based lookup, no writes

**File**: `retail/templates/models.py` (read-only context — no
schema change ships against this model).

### Schema change

**None.** The model is untouched.

### Read sites

For each matched IntegratedAgent in the fan-out, the use case
issues one queryset against `Template`:

```python
# DirectSendCategoryWebhookUseCase._lookup_template (illustrative)
integrated_agent.templates.select_related("current_version").filter(
    name=dto.template_name,
).first()
```

- **Name lookup**: `Template.name == dto.template_name` — exact
  match, case-sensitive (FR-005). The `name` column is
  `CharField` (not indexed, but the IntegratedAgent's
  `templates` reverse-accessor scopes the query to the small set
  of templates owned by that IntegratedAgent, so a sequential scan
  is cheap — typically 4 rows for the OrderStatus fleet).
- **`.select_related("current_version")`**: eager-loads the
  `current_version` OneToOne FK in the same query (Decision 4).
- **`.first()`**: returns `None` when no Template matches; routes
  through the `template_not_found` audit-log branch per FR-005.
- **No `is_active=True` filter**: the Template's `is_active` flag
  is a soft-delete marker; an incorrect-category determination
  applies to the template content even if the template was
  soft-deleted at some point. Filtering on `is_active=True` would
  silently desync soft-deleted templates from a category-correctness
  signal.

### Write sites

**None.** The Template row is never mutated. FR-007a is explicit:
"the Template still points at the same Version row; only the status
string is updated". The `current_version` FK is read but not
written.

### Untouched columns

All 14 columns on `Template` (`uuid`, `name`, `parent`,
`current_version`, `rule_code`, `integrated_agent`, `metadata`,
`needs_button_edit`, `deleted_at`, `is_active`, `start_condition`,
`display_name`, `variables`, `config`). The `uuid` field has
`primary_key=True` (legacy pattern), so Django adds no implicit `id`
column on this model.

---

## 4. `Project` — tenant boundary lookup

**File**: `retail/projects/models.py` (read-only context — no
schema change ships against this model).

### Schema change

**None.** The model is untouched.

### Read sites

The Project is consulted transitively via the IntegratedAgent
queryset's `project__uuid == dto.project_uuid` clause (Decision 3).
The use case does NOT issue a separate
`Project.objects.get(uuid=...)` query — the JOIN through
`project__uuid` is sufficient and avoids the "project not found"
case as a distinct outcome (a non-existent `project_uuid` simply
returns zero IntegratedAgents from the fan-out queryset, which
routes through `no_matching_integrated_agent` per FR-004b).

The Project's `is_blocked` flag is **NOT** consulted (Edge Case row
in spec.md): "the webhook still processes the event and updates the
template's status. Blocking a project (`Project.is_blocked`) gates
outbound flows (broadcasts, billing) — it does not gate inbound
state-correctness signals like this category-detection webhook".

### Write sites

**None.**

### Untouched columns

All 8 columns on `Project` (`name`, `uuid`, `organization_uuid`,
`vtex_account`, `language`, `config`, `is_blocked`, plus the
implicit `id`).

---

## 5. In-memory DTOs

The feature introduces four in-memory dataclasses, all under
`retail/webhooks/templates/usecases/direct_send_category.py`. None
of them is persisted; all are short-lived data carriers between the
view, the serializer, the use case, and the audit-log helper.

### 5.1 `DirectSendCategoryDTO` — inbound payload

```python
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class DirectSendCategoryDTO:
    """Validated, immutable payload passed from the view to the use case.

    Built by the view from the serializer's ``validated_data``;
    consumed by ``DirectSendCategoryWebhookUseCase.execute(...)``.
    Carries the five required fields pinned by FR-003.
    """

    project_uuid: UUID
    app_uuid: UUID
    template_name: str
    template_category: str
    template_correct_category: str
```

**Validation**: handled by the serializer (Decision 9). The DTO
itself does no validation — it relies on the serializer's
`is_valid(raise_exception=True)` having succeeded.

**Field-by-field semantics**:

| Field                       | Type   | Source                       | Notes                                                                                                                                            |
| --------------------------- | ------ | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `project_uuid`              | `UUID` | `serializers.UUIDField`      | Matches `Project.uuid` (`unique=True`). Used in the IntegratedAgent fan-out clause (Decision 3).                                                |
| `app_uuid`                  | `UUID` | `serializers.UUIDField`      | Matches `Version.integrations_app_uuid`. Used in the JOIN clause (Decision 2).                                                                  |
| `template_name`             | `str`  | `serializers.CharField`      | Compared case-sensitive against `Template.name` (FR-005). Empty string is rejected at the serializer level (`allow_blank=False`).             |
| `template_category`         | `str`  | `serializers.CharField`      | Captured verbatim on every audit-log `k=v` payload for diagnostic visibility. Does NOT participate in the FR-006 flagging decision under the single-field eligibility model (Clarifications session 2026-05-25 Q3). No normalization (spec.md A3).      |
| `template_correct_category` | `str`  | `serializers.CharField`      | Compared as-is against the literal `"UTILITY"` (FR-006 / FR-006a). Sole driver of the FR-006 single-field flagging condition. No normalization (spec.md A3).                                    |

### 5.2 `DirectSendCategoryResult` — outbound response shape

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class DirectSendCategoryResult:
    """Use-case return value shaped for the HTTP 200 response body.

    The view shapes the HTTP body as ``Response(result.to_dict(), 200)``.
    The two counters MUST equal the same values emitted on the
    FR-009c ``completed`` audit-log line (FR-010 last sentence).
    """

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

**Counters semantics** (per the FR-010 amendment — direction-agnostic
counter):

| Counter                       | Increment rule                                                                                                                          |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `templates_updated`           | Incremented once per Version whose `status` is written by this request, regardless of direction — `+1` for each `flagged` event (`* → "FLAGGED"` write per FR-007) and `+1` for each `auto_demoted` event (`"FLAGGED" → "APPROVED"` write per FR-007d). Replays and no-action paths do NOT increment: `flag_replay_noop` and `no_action_required` are pure observations and issue no `Version.save`. Operators distinguish the two write directions via the audit-log `event_name` token, NOT via the counter. |
| `integrated_agents_inspected` | Equals the size of the fan-out queryset (Decision 2's `.distinct()` count). On the `no_matching_integrated_agent` path the counter is `0` and the response body still includes both keys with value `0`. |

**`detail` shape**:

The `detail` string is a short human-readable summary keyed off the
dominant outcome. The closed enumeration is:

- `"Templates flagged."` — at least one Version was transitioned
  to `"FLAGGED"` and all observed outcomes belong to the flag
  family (`flagged`, `flag_replay_noop`).
- `"Auto-demoted."` — at least one Version was transitioned from
  `"FLAGGED"` to `"APPROVED"` (FR-006c / FR-007d) and all observed
  outcomes belong to the demote-or-no-op family (`auto_demoted`,
  `no_action_required`).
- `"Already flagged."` — every matched Version was already
  `FLAGGED` AND the payload was a flagging payload (every line
  emitted `flag_replay_noop`); no write occurred.
- `"No action required."` — every matched IntegratedAgent's
  Template passed the flagging condition without firing
  (`template_correct_category == "UTILITY"`, regardless of
  `template_category`) AND no Version was in `"FLAGGED"` (so the
  auto-demote branch did not fire either).
- `"No matching IntegratedAgent."` — the fan-out queryset returned
  zero IntegratedAgents (FR-004b).
- `"Template not found."` — every matched IntegratedAgent had no
  Template named `template_name` (every line emitted
  `template_not_found`) or the matched Template had no
  `current_version` (`template_has_no_current_version` per FR-005a).
- `"Mixed outcomes."` — the fan-out across multiple
  IntegratedAgents produced more than one of the above outcomes.
  Examples: (a) IA-1 flagged but IA-2 had no Template
  (US1 scenario 4 variant); (b) IA-1's `APPROVED` Version followed
  the `no_action_required` path while IA-2's `FLAGGED` Version was
  auto-demoted under the same `UTILITY/UTILITY` payload (the
  heterogeneous-status fan-out case from `spec.md §Edge Cases`).
  Any time the per-IA outcome set has cardinality > 1, this is the
  result; operators consult the per-IA audit-log lines for the
  breakdown.

The closed enumeration is operator-facing context; operator
dashboards filter on the structured audit-log `event_name` token
(FR-009a), not on this string.

### 5.3 `FlaggingReason` — closed enumeration

```python
from enum import Enum


class FlaggingReason(str, Enum):
    """Closed enumeration for the ``reason=`` k=v on ``flagged`` audit-log lines.

    Pinned by FR-006b / FR-009a. Additive-only: new reasons MAY be
    added; existing reasons MUST NOT be renamed or removed.

    Collapsed to a single variant by Clarifications session
    2026-05-25 Q3 (single-field eligibility model). Under the
    single-clause flag rule (``template_correct_category != "UTILITY"``)
    there is only one reason that can fire whenever the flag branch
    is taken; the prior three-variant enumeration (``CATEGORY_MISMATCH``,
    ``CATEGORY_NOT_UTILITY``, ``CATEGORY_MISMATCH_AND_NOT_UTILITY``)
    is retired.
    """

    CORRECT_CATEGORY_NOT_UTILITY = "correct_category_not_utility"
```

**Determination rule** (FR-006 / FR-006b):

| `template_correct_category != "UTILITY"` | Reason emitted on the `flagged` audit line |
| ---------------------------------------- | ------------------------------------------ |
| `False`                                  | (flagging condition does not fire — `no_action_required` against an `APPROVED` Version, or `auto_demoted` against a `FLAGGED` Version per FR-006c) |
| `True`                                   | `CORRECT_CATEGORY_NOT_UTILITY` (the constant single value) |

`template_category` is NOT consulted by the determination rule —
it is captured verbatim on every audit-log `k=v` payload (FR-009d)
for diagnostic visibility but does not participate in the
flag-or-demote decision.

### 5.4 `EventName` — closed enumeration

```python
from enum import Enum


class EventName(str, Enum):
    """Closed enumeration for the ``event_name`` discriminator immediately
    after the ``[DirectSendCategoryWebhook]`` tag in every audit-log line.

    Pinned by FR-009a. Additive-only.
    """

    RECEIVED = "received"
    FLAGGED = "flagged"
    FLAG_REPLAY_NOOP = "flag_replay_noop"
    NO_ACTION_REQUIRED = "no_action_required"
    AUTO_DEMOTED = "auto_demoted"
    NO_MATCHING_INTEGRATED_AGENT = "no_matching_integrated_agent"
    TEMPLATE_NOT_FOUND = "template_not_found"
    TEMPLATE_HAS_NO_CURRENT_VERSION = "template_has_no_current_version"
    COMPLETED = "completed"
    UNEXPECTED_ERROR = "unexpected_error"
```

**Emission rules**: see `spec.md` FR-009a–d for the per-event log-level
discipline (`info` vs `warning` vs `error`), the required `k=v`
fields per event, and the per-request emission sequence.

The closed enumeration is the contract surface for operator
dashboards (FR-009a) and is additive-only: new tokens MAY be added
in future PRs, existing tokens MUST NOT be renamed or removed.

---

## 6. Read / write summary table

For reviewer audit purposes — the complete inventory of model
interactions:

| Model              | Read sites                                                                                  | Write sites                                  | Schema change |
| ------------------ | ------------------------------------------------------------------------------------------- | -------------------------------------------- | ------------- |
| `Project`          | Transitively via `IntegratedAgent.objects.filter(project__uuid=...)`                        | None                                         | None          |
| `IntegratedAgent`  | `IntegratedAgent.objects.filter(project__uuid=..., templates__versions__integrations_app_uuid=...).distinct()`; transitively `agent.uuid`, `agent.project.uuid` on the audit-log emission. | None                                         | None          |
| `Template`         | `integrated_agent.templates.select_related("current_version").filter(name=...).first()`; transitively `template.uuid` on the audit-log emission. | None                                         | None          |
| `Version`          | `template.current_version` (status, uuid) via `select_related`; `versions__integrations_app_uuid` on the IntegratedAgent fan-out queryset. | Two write targets, mutually exclusive per request and per Version: (a) `version.status = "FLAGGED"; version.save(update_fields=["status"])` — fires when `version.status != "FLAGGED"` AND the FR-006 single-field flagging condition is true (`template_correct_category != "UTILITY"`; FR-007 / FR-007b). (b) `version.status = "APPROVED"; version.save(update_fields=["status"])` — fires when `version.status == "FLAGGED"` AND the FR-006 flagging condition is false (`template_correct_category == "UTILITY"`; auto-demote, FR-006c / FR-007d). `template_category` is captured for audit only and does NOT participate in either gate (Clarifications session 2026-05-25 Q3). Exactly one column on one row per matched Template per request. | None          |

**Migration count**: 0.
**New constraint count**: 0.
**New index count**: 0.
**Net DDL delta**: empty.
