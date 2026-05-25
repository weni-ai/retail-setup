# Contract — Direct Send Template Incorrect-Category Webhook (inbound)

**Feature**: `003-template-category-webhook`
**Producer**: Integrations Engine — calls Retail when Meta-side
category-detection determines that a Direct Send template's category
is wrong.
**Consumer**: `retail-setup` — `DirectSendCategoryWebhook`
(new view).
**Endpoint**: `POST {RETAIL_BASE_URL}/webhook/templates-status/api/category-notification/`
**Auth**: Internal-communication permission
(`CanCommunicateInternally` — same gate used by the existing
`TemplatesStatusWebhook` at
`retail/webhooks/templates/views/template_status_update.py:21`).

This document pins the inbound HTTP contract between Integrations
and Retail for the v1 incorrect-category notification. Retail is
the consumer; Integrations owns the upstream filtering (FR-012) and
the namespace of `template_category` values (spec.md A3).

---

## 1. Request

```http
POST /webhook/templates-status/api/category-notification/ HTTP/1.1
Authorization: Bearer {INTERNAL_TOKEN}
Content-Type: application/json

{
  "project_uuid":              "11111111-1111-1111-1111-111111111111",
  "app_uuid":                  "22222222-2222-2222-2222-222222222222",
  "template_name":             "weni_order_invoiced",
  "template_category":         "MARKETING",
  "template_correct_category": "MARKETING"
}
```

### 1.1 Required headers

| Header           | Value                                                                                                    | Notes                                                                                                                                            |
| ---------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Authorization`  | `Bearer <INTERNAL_TOKEN>`                                                                                | Token belonging to a user with the Django permission code-name `can_communicate_internally`. Same token shape as the existing `TemplatesStatusWebhook`. |
| `Content-Type`   | `application/json`                                                                                       | DRF rejects non-JSON content types with HTTP 415; Integrations always sends JSON.                                                               |

No project-scoped header (`Project-Uuid`) is required — the
`project_uuid` field inside the payload is the authoritative tenant
identifier for the lookup (FR-002).

### 1.2 Body fields (all required)

| Field                       | Type   | Required | Allow blank | Notes                                                                                                                                            |
| --------------------------- | ------ | -------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `project_uuid`              | UUID   | yes      | no          | Matches `Project.uuid`. Used as the tenant scoping clause in the IntegratedAgent fan-out (FR-004 / SC-006). Missing or malformed → HTTP 400.    |
| `app_uuid`                  | UUID   | yes      | no          | Matches `Version.integrations_app_uuid`. Used as the app-linkage clause in the IntegratedAgent fan-out (FR-004). Missing or malformed → HTTP 400. |
| `template_name`             | string | yes      | no          | Local `Template.name`. Compared case-sensitively. Empty string → HTTP 400 (the serializer's `allow_blank=False`).                                |
| `template_category`         | string | yes      | no          | Category Meta reports the template currently has. Compared as-is against `template_correct_category` and `"UTILITY"` (FR-006 / FR-006a). Empty string → HTTP 400. |
| `template_correct_category` | string | yes      | no          | Category Meta says the template SHOULD have. Compared as-is against `template_category` (FR-006). Empty string → HTTP 400.                       |

### 1.3 Unknown fields

Unknown JSON keys MUST be ignored silently (DRF's default
serializer behaviour). This is the forward-compatibility surface:
if Integrations ever adds a new field (e.g. `detected_at`), Retail
ignores it without rejecting the request. The serializer does NOT
declare `extra_fields = "raise"` or equivalent.

### 1.4 Value namespace

- `template_category` / `template_correct_category` values are
  NOT validated against an allow-list (FR-003a). Integrations owns
  the category-value namespace (spec.md A3); Retail does not
  normalize and does not reject unknown values.
- Concrete v1 examples observed in practice:
  `"UTILITY"`, `"MARKETING"`, `"AUTHENTICATION"`. The literal
  `"UTILITY"` (uppercase, no whitespace) is the only value for
  which the second clause of the flagging condition is `False`
  (FR-006a).
- The webhook does NOT case-fold or whitespace-trim either field —
  lowercase `"utility"` is NOT equal to the literal `"UTILITY"`
  and therefore triggers the `category_not_utility` clause
  (Edge Case row in spec.md).

---

## 2. Successful response

HTTP 200 with body:

```jsonc
{
  "detail":                       "Templates flagged.",
  "templates_updated":            1,
  "integrated_agents_inspected":  1
}
```

### 2.1 Response shape

| Field                         | Type    | Required | Notes                                                                                                                                            |
| ----------------------------- | ------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `detail`                      | string  | yes      | Short human-readable summary keyed off the dominant outcome. The closed enumeration is pinned in `data-model.md §5.2`.                            |
| `templates_updated`           | integer | yes      | Count of Version rows transitioned to `"FLAGGED"` by this request. Replays and no-action paths increment by 0 (FR-010, FR-009d `completed`).      |
| `integrated_agents_inspected` | integer | yes      | Count of IntegratedAgents the fan-out queryset returned. On `no_matching_integrated_agent` this is `0`; the field is still present.              |

Additional fields MAY be added by future PRs (additive-only — the
spec's FR-010 explicitly allows "Optional additional fields … MAY be
included"). Future fields MUST NOT cause Integrations-side parsers
to break; Integrations consumes the response opportunistically (for
operator dashboards) and is not contract-bound to a closed key set.

### 2.2 Counter parity with the audit log

The two counters in the response body MUST equal the values emitted
on the FR-009c `completed` audit-log line for the same request.
The audit log line looks like:

```text
[DirectSendCategoryWebhook] completed: project_uuid=... app_uuid=... template_name=... templates_updated=1 integrated_agents_inspected=1
```

(see FR-009d's `completed` row). Both views — the HTTP response
body and the `completed` log line — are projections of the same
two counters computed by the use case.

### 2.3 Outcome-to-shape mapping

| Outcome                                                                                       | `templates_updated` | `integrated_agents_inspected` | `detail`                              |
| --------------------------------------------------------------------------------------------- | ------------------- | ----------------------------- | ------------------------------------- |
| One IntegratedAgent's Template was flagged.                                                   | `1`                 | `1`                           | `"Templates flagged."`                |
| Two IntegratedAgents both flagged for the same template (US1 scenario 4).                     | `2`                 | `2`                           | `"Templates flagged."`                |
| Replay: matched Version is already `FLAGGED`, flagging condition fires.                       | `0`                 | `1`                           | `"Already flagged."`                  |
| Non-flagging payload, matched Version is `APPROVED` (US1 scenario 3 / FR-006 no-fire case).   | `0`                 | `1`                           | `"No action required."`               |
| Non-flagging payload, matched Version is already `FLAGGED` (US2 AS2 — auto-demote per FR-006c / FR-007d). | `1`                 | `1`                           | `"Auto-demoted."`                     |
| Non-flagging payload re-fired against a Version already `APPROVED` (post-demote settling — FR-008 last clause). | `0`                 | `1`                           | `"No action required."`               |
| The fan-out queryset returned zero IntegratedAgents (FR-004b / US3 scenario 1).              | `0`                 | `0`                           | `"No matching IntegratedAgent."`      |
| One IntegratedAgent matched but had no Template named `template_name` (FR-005 / US3 scenario 2). | `0`                 | `1`                           | `"Template not found."`              |
| Matched Template has no `current_version` (FR-005a / US3 scenario 3).                         | `0`                 | `1`                           | `"Template not found."` *             |
| Multiple IntegratedAgents with mixed outcomes (e.g. IA-1 flagged, IA-2 had no Template; or IA-1 `no_action_required` + IA-2 `auto_demoted`). | `≥1`                | `≥2`                          | `"Mixed outcomes."`                   |

\* The `template_has_no_current_version` audit event is a
defensively-handled inconsistent state; the response `detail`
collapses to `"Template not found."` since the operator-facing
distinction lives in the audit log, not the HTTP body.

---

## 3. Failure modes

### 3.1 HTTP 400 — malformed request

Returned by DRF when the serializer's
`is_valid(raise_exception=True)` fails. Body shape is DRF's
default:

```jsonc
{
  "project_uuid": ["This field is required."],
  "template_category": ["This field may not be blank."]
}
```

| Sub-class                                          | Trigger                                                                                                                                          |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Missing required field                             | Any of the five fields absent from the body.                                                                                                     |
| Malformed UUID                                     | `project_uuid` or `app_uuid` is not parseable as a UUID.                                                                                         |
| Blank string                                       | `template_name` / `template_category` / `template_correct_category` is the empty string (`allow_blank=False` on the serializer).                |
| Non-JSON content type                              | DRF auto-rejects via `Content-Type: application/json` requirement.                                                                                |
| JSON parse error                                   | Malformed JSON body — DRF returns HTTP 400 with `"detail": "JSON parse error - <message>"`.                                                       |

The webhook does NOT log a structured audit entry for HTTP 400
responses (DRF's standard 400 logging via Django's
`django.request` logger is sufficient — spec.md Edge Cases row 1).

### 3.2 HTTP 401 / 403 — authentication failure

Returned by DRF's permission layer when:

- `Authorization` header is missing → HTTP 401.
- Token belongs to a user without the
  `can_communicate_internally` permission → HTTP 403.

No custom handling is added; the response is shaped by DRF's
default exception handler. No audit-log entry is emitted by Retail.

### 3.3 HTTP 500 — genuinely unexpected exception

Returned when the use case's outer `try / except Exception as exc`
catches an unexpected exception (e.g. database connection lost
mid-request, OperationalError, IntegrityError from a concurrent
migration). Body shape:

```jsonc
{
  "detail": "Internal server error"
}
```

The webhook emits one `unexpected_error` audit-log line with
`exc_info=True` (FR-009b last clause / FR-010b):

```text
[DirectSendCategoryWebhook] unexpected_error: project_uuid=... app_uuid=... template_name=... error=<str(exc)>
```

(plus the Python traceback emitted by the logging stdlib's
`exc_info=True` mechanism).

Domain-level "couldn't find X" cases are explicitly NOT HTTP 500 —
they return HTTP 200 with `templates_updated=0` per FR-004b /
FR-005 / FR-005a.

---

## 4. Idempotency

The webhook is idempotent at the Version level (FR-008).

- **Same flagging-payload retry against a Version already `FLAGGED`**:
  the dispatcher routes to `flag_replay_noop` — no `Version.save`,
  audit line `flag_replay_noop`, response shape
  `templates_updated=0`, `detail="Already flagged."`.
- **Corrected-category payload (`UTILITY/UTILITY`) against a Version
  already `FLAGGED`** (FR-006c / FR-007d): the dispatcher routes to
  the auto-demote branch — writes `status="APPROVED"`, audit line
  `auto_demoted` with `previous_status=FLAGGED new_status=APPROVED`,
  response shape `templates_updated=1`, `detail="Auto-demoted."`.
  The dispatch gate from spec 002's `Broadcast.get_current_template`
  re-admits the template on the next broadcast attempt with no
  operator action required.
- **Corrected-category payload re-fired against a Version already
  `APPROVED`** (post-demote settling): the FR-006 flagging
  condition is false AND the Version is not `FLAGGED`, so the
  dispatcher routes to `no_action_required` — no `Version.save`,
  audit line `no_action_required`, response shape
  `templates_updated=0`, `detail="No action required."` This
  convergence is required by FR-008 last clause.
- **Concurrent same-payload calls**: Django's default transaction
  isolation serializes the UPDATEs. For a flagging payload against
  an `APPROVED` Version, both calls converge on `FLAGGED` — one
  call observes `APPROVED` and issues the UPDATE, the other
  observes `FLAGGED` and routes through `flag_replay_noop`. The
  audit log records one `flagged` entry and one `flag_replay_noop`
  entry. Symmetric convergence holds for a corrected-category
  payload against a `FLAGGED` Version (one `auto_demoted`, one
  `no_action_required`).
- **Replay window**: unbounded. There is no dedup cache, no
  sliding-window suppression. The upstream courier (per spec.md
  US2) MAY replay events hours / days later; Retail observes the
  current state of `Version.status` and routes through the
  appropriate audit-log branch.
- **No `Idempotency-Key` header is required**. The contract is
  idempotent by row-state convergence, not by an
  out-of-band dedup key.

---

## 5. Cross-tenant isolation

The webhook honours the SC-006 cross-tenant boundary (FR-004,
spec.md Edge Cases row 9).

- **Same `app_uuid` in different projects**: the IntegratedAgent
  queryset's `project__uuid=dto.project_uuid` clause excludes
  matches in other projects. The audit log records
  `no_matching_integrated_agent` for the named project; no
  reference to the IntegratedAgent in the other project is
  emitted (FR-009d's `no_matching_integrated_agent` row carries
  ONLY the five payload values).
- **Project marked `is_blocked=True`**: the webhook still
  processes the event (spec.md Edge Cases row 12). Project
  blocking gates outbound flows (broadcasts, billing), not inbound
  state-correctness signals.

---

## 6. Examples

### 6.1 Happy path — single IntegratedAgent, flagging condition fires (US1 scenario 1)

**Request**:

```json
{
  "project_uuid":              "11111111-1111-1111-1111-111111111111",
  "app_uuid":                  "22222222-2222-2222-2222-222222222222",
  "template_name":             "weni_order_invoiced",
  "template_category":         "MARKETING",
  "template_correct_category": "MARKETING"
}
```

**Response**: `HTTP 200`

```json
{
  "detail":                       "Templates flagged.",
  "templates_updated":            1,
  "integrated_agents_inspected":  1
}
```

**Audit log**:

```text
[DirectSendCategoryWebhook] received: project_uuid=11111111-... app_uuid=22222222-... template_name=weni_order_invoiced template_category=MARKETING template_correct_category=MARKETING
[DirectSendCategoryWebhook] flagged: project_uuid=11111111-... app_uuid=22222222-... template_name=weni_order_invoiced template_category=MARKETING template_correct_category=MARKETING integrated_agent_uuid=33333333-... template_uuid=44444444-... version_uuid=55555555-... previous_status=APPROVED new_status=FLAGGED reason=category_not_utility
[DirectSendCategoryWebhook] completed: project_uuid=11111111-... app_uuid=22222222-... template_name=weni_order_invoiced templates_updated=1 integrated_agents_inspected=1
```

### 6.2 Flagging-payload replay — Version already FLAGGED (US2 scenario 1)

Same request as 6.1, fired a second time.

**Response**: `HTTP 200`

```json
{
  "detail":                       "Already flagged.",
  "templates_updated":            0,
  "integrated_agents_inspected":  1
}
```

**Audit log**:

```text
[DirectSendCategoryWebhook] received: ...
[DirectSendCategoryWebhook] flag_replay_noop: project_uuid=... app_uuid=... template_name=... template_category=MARKETING template_correct_category=MARKETING integrated_agent_uuid=... template_uuid=... version_uuid=... previous_status=FLAGGED
[DirectSendCategoryWebhook] completed: project_uuid=... app_uuid=... template_name=... templates_updated=0 integrated_agents_inspected=1
```

### 6.2a Auto-demote — corrected-category replay against a FLAGGED Version (US2 AS2 / FR-006c)

After 6.1 has flipped the Version to `FLAGGED`, the operator fixes
the template content on the Meta side so the category is now
`UTILITY`. Integrations re-fires the webhook with the corrected
payload:

**Request**:

```json
{
  "project_uuid":              "11111111-1111-1111-1111-111111111111",
  "app_uuid":                  "22222222-2222-2222-2222-222222222222",
  "template_name":             "weni_order_invoiced",
  "template_category":         "UTILITY",
  "template_correct_category": "UTILITY"
}
```

**Response**: `HTTP 200`

```json
{
  "detail":                       "Auto-demoted.",
  "templates_updated":            1,
  "integrated_agents_inspected":  1
}
```

**Audit log**:

```text
[DirectSendCategoryWebhook] received: ...
[DirectSendCategoryWebhook] auto_demoted: project_uuid=... app_uuid=... template_name=... template_category=UTILITY template_correct_category=UTILITY integrated_agent_uuid=... template_uuid=... version_uuid=... previous_status=FLAGGED new_status=APPROVED
[DirectSendCategoryWebhook] completed: project_uuid=... app_uuid=... template_name=... templates_updated=1 integrated_agents_inspected=1
```

A second invocation with the same `UTILITY/UTILITY` payload (now
against the post-demote `APPROVED` Version) routes through the
`no_action_required` path: HTTP 200, `templates_updated=0`,
`detail="No action required."`, audit line `no_action_required`.

### 6.3 No-action — UTILITY/UTILITY (US1 scenario 3)

**Request**:

```json
{
  "project_uuid":              "11111111-1111-1111-1111-111111111111",
  "app_uuid":                  "22222222-2222-2222-2222-222222222222",
  "template_name":             "weni_order_invoiced",
  "template_category":         "UTILITY",
  "template_correct_category": "UTILITY"
}
```

**Response**: `HTTP 200`

```json
{
  "detail":                       "No action required.",
  "templates_updated":            0,
  "integrated_agents_inspected":  1
}
```

**Audit log**:

```text
[DirectSendCategoryWebhook] received: ...
[DirectSendCategoryWebhook] no_action_required: project_uuid=... app_uuid=... template_name=... template_category=UTILITY template_correct_category=UTILITY integrated_agent_uuid=... template_uuid=... version_uuid=... previous_status=APPROVED
[DirectSendCategoryWebhook] completed: project_uuid=... app_uuid=... template_name=... templates_updated=0 integrated_agents_inspected=1
```

### 6.4 Misrouted — no matching IntegratedAgent (US3 scenario 1)

**Request**: a `project_uuid` that exists but whose IntegratedAgents'
Versions do NOT carry the requested `app_uuid`.

**Response**: `HTTP 200`

```json
{
  "detail":                       "No matching IntegratedAgent.",
  "templates_updated":            0,
  "integrated_agents_inspected":  0
}
```

**Audit log**:

```text
[DirectSendCategoryWebhook] received: ...
[DirectSendCategoryWebhook] no_matching_integrated_agent: project_uuid=... app_uuid=... template_name=... template_category=... template_correct_category=...
[DirectSendCategoryWebhook] completed: project_uuid=... app_uuid=... template_name=... templates_updated=0 integrated_agents_inspected=0
```

### 6.5 Multi-IntegratedAgent fan-out — both flagged (US1 scenario 4)

**Request**: same shape as 6.1 — `project_uuid` references a
project with two IntegratedAgents (IA-1 active + IA-2 inactive)
both linked to the same `app_uuid` and both owning a Template
named `weni_order_invoiced`.

**Response**: `HTTP 200`

```json
{
  "detail":                       "Templates flagged.",
  "templates_updated":            2,
  "integrated_agents_inspected":  2
}
```

**Audit log**:

```text
[DirectSendCategoryWebhook] received: ...
[DirectSendCategoryWebhook] flagged: ... integrated_agent_uuid=<IA-1> template_uuid=<T-IA1> version_uuid=<V-IA1> previous_status=APPROVED new_status=FLAGGED reason=category_not_utility
[DirectSendCategoryWebhook] flagged: ... integrated_agent_uuid=<IA-2> template_uuid=<T-IA2> version_uuid=<V-IA2> previous_status=APPROVED new_status=FLAGGED reason=category_not_utility
[DirectSendCategoryWebhook] completed: ... templates_updated=2 integrated_agents_inspected=2
```

### 6.6 Mixed outcomes — IA-1 flagged, IA-2 has no Template

**Request**: same as 6.5, but IA-2 has been mutated such that its
Template named `weni_order_invoiced` no longer exists (e.g. a soft
delete cascade observed in production).

**Response**: `HTTP 200`

```json
{
  "detail":                       "Mixed outcomes.",
  "templates_updated":            1,
  "integrated_agents_inspected":  2
}
```

**Audit log**:

```text
[DirectSendCategoryWebhook] received: ...
[DirectSendCategoryWebhook] flagged: ... integrated_agent_uuid=<IA-1> template_uuid=<T-IA1> version_uuid=<V-IA1> previous_status=APPROVED new_status=FLAGGED reason=category_not_utility
[DirectSendCategoryWebhook] template_not_found: project_uuid=... app_uuid=... template_name=weni_order_invoiced integrated_agent_uuid=<IA-2>
[DirectSendCategoryWebhook] completed: ... templates_updated=1 integrated_agents_inspected=2
```

### 6.7 Malformed request — missing `template_correct_category`

**Request**:

```json
{
  "project_uuid":      "11111111-1111-1111-1111-111111111111",
  "app_uuid":          "22222222-2222-2222-2222-222222222222",
  "template_name":     "weni_order_invoiced",
  "template_category": "MARKETING"
}
```

**Response**: `HTTP 400`

```json
{
  "template_correct_category": ["This field is required."]
}
```

No audit-log entry is emitted (DRF's `django.request` logger
handles the request rejection).

---

## 7. Operator observability

Operators monitor the webhook via the `[DirectSendCategoryWebhook]`
log tag (FR-009 — same tag-based filtering convention as
`[CART_SERVICE]`, `[ORDER_STATUS]`, `[CONVERSION_TRACKING]`, and
spec 002's `[BroadcastDispatch]` / `[DirectSend]`). The closed
`event_name` enumeration (FR-009a) is the operator dashboard's
primary discriminator; recommended saved searches:

- `[DirectSendCategoryWebhook] flagged: ...` — rate of new
  flagging events; expected to spike during a Meta-driven
  re-categorization wave, otherwise near-zero.
- `[DirectSendCategoryWebhook] no_matching_integrated_agent: ...`
  — rate of misrouted events; expected near-zero in steady state,
  a non-zero rate indicates either an upstream Integrations bug
  or stale data on the Integrations side.
- `[DirectSendCategoryWebhook] unexpected_error: ...` — should
  always be zero; any occurrence is a Retail-side bug that
  warrants paging.

---

## 8. Versioning

The contract is v1. Future changes follow these rules:

- **Adding a new optional request field**: backward-compatible.
  Integrations can roll out the new field at its own pace; Retail
  ignores unknown keys per §1.3.
- **Adding a new required request field**: backward-incompatible.
  Requires a coordinated deploy (Retail rolls out the new field
  as accepted, then Integrations starts sending it) and a spec
  amendment to FR-003.
- **Adding a new `event_name` token to the audit-log enumeration**:
  backward-compatible (additive-only per FR-009a). Operator
  dashboards that filter on existing tokens continue to work.
- **Renaming or removing an existing `event_name` token**:
  forbidden (FR-009a last clause — additive-only).
- **Adding a new response field**: backward-compatible (per
  §2.1). Integrations consumes the response opportunistically.
- **Renaming or removing an existing response field
  (`detail`, `templates_updated`, `integrated_agents_inspected`)**:
  backward-incompatible. Requires a spec amendment to FR-010.

The Retail Engineering team is the contract owner; the Integrations
Engineering team is the consumer. Spec amendments flow through
`/speckit-specify` → `/speckit-plan` → coordinated deploy.
