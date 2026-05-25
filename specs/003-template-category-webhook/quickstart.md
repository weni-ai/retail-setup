# Quickstart — Direct Send Template Incorrect-Category Webhook

**Feature**: `003-template-category-webhook`
**Spec**: `./spec.md`
**Plan**: `./plan.md`

This is the operator / engineer "happy path" walkthrough that
validates the feature end-to-end against a real Direct Send-enabled
WhatsApp Cloud channel. Each step maps to one or more acceptance
scenarios from `spec.md`.

---

## 0. Prerequisites

| Item                                                                                            | Where it lives                                                                   |
| ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Spec 002 (`002-direct-send-broadcasts`) is deployed.                                            | The `FLAGGED` enum value on `Version.STATUS_CHOICES` and the dispatch-gate skip behaviour live in spec 002. |
| The OrderStatus agent has been pushed and assigned to the project (existing flow).              | `POST /api/v3/agents/push/` + `POST /api/v3/agents/{uuid}/assign/`              |
| The project has a WhatsApp Cloud channel created via the existing onboarding flow.              | Integrations Engine — `apptype=wpp-cloud`                                       |
| The channel has been opted into the Direct Send Beta and Integrations has set                    | Integrations DB — `App.config.direct_send = True`                               |
| `config.direct_send = True` on the channel-app.                                                  |                                                                                  |
| At least one local `Template` exists on the assigned IntegratedAgent with                       | `retail/templates/models.py` — created at assignment time by                    |
| `current_version.status = "APPROVED"` and at least one `Version` carrying                       | `AssignAgentUseCase._create_library_templates`                                  |
| `integrations_app_uuid` equal to the channel's `app_uuid`.                                       |                                                                                  |
| A user / service-account exists with the Django permission code-name                            | Granted via `python manage.py shell` and the                                    |
| `can_communicate_internally` (same gate as the existing `TemplatesStatusWebhook`).               | `BaseTestMixin.setup_internal_user_permissions` helper at test time.            |

---

## 1. Run migrations

```bash
poetry run python manage.py migrate
```

**Zero** new migrations are applied — this feature ships no schema
change (spec.md A10, `data-model.md`). The pre-existing
`templates.0017_alter_version_status_paused_flagged` migration
(shipped by spec 002) is the only DDL dependency, and it is
already applied in any environment running spec 002.

---

## 2. Pre-flight: confirm the local Template + Version state

Before firing the webhook, capture the baseline:

```bash
poetry run python manage.py shell <<'PY'
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.projects.models import Project

project = Project.objects.get(uuid="11111111-1111-1111-1111-111111111111")
agents = IntegratedAgent.objects.filter(
    project=project,
    templates__versions__integrations_app_uuid="22222222-2222-2222-2222-222222222222",
).distinct()

for agent in agents:
    template = agent.templates.filter(name="weni_order_invoiced").first()
    if template and template.current_version:
        print(
            f"agent={agent.uuid} template={template.uuid} "
            f"version={template.current_version.uuid} "
            f"status={template.current_version.status}"
        )
PY
```

**Expected pre-flight output** (one line per matched IntegratedAgent):

```text
agent=33333333-... template=44444444-... version=55555555-... status=APPROVED
```

The shell snippet above mirrors the use case's lookup logic
(Decision 2 + Decision 4 in `research.md`); a divergent result
indicates either (a) an upstream Integrations bug that misrouted
the webhook, or (b) a local-state inconsistency that the webhook
will defensively skip via `no_matching_integrated_agent` /
`template_not_found` / `template_has_no_current_version` per
FR-004b / FR-005 / FR-005a.

---

## 3. Fire the webhook — flagging condition fires (US1 scenario 1)

```bash
curl -X POST "$BASE_URL/webhook/templates-status/api/category-notification/" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  --data-raw '{
    "project_uuid":              "11111111-1111-1111-1111-111111111111",
    "app_uuid":                  "22222222-2222-2222-2222-222222222222",
    "template_name":             "weni_order_invoiced",
    "template_category":         "MARKETING",
    "template_correct_category": "MARKETING"
  }'
```

### Expected outcome

- **HTTP status**: `200 OK`.
- **Response body**:
  ```json
  {
    "detail":                       "Templates flagged.",
    "templates_updated":            1,
    "integrated_agents_inspected":  1
  }
  ```
- **Database side effect**: exactly one `UPDATE` against
  `templates_version.status` for the matched Version row; new
  value `"FLAGGED"`. The Template's `current_version` FK is
  unchanged (FR-007a).
- **Audit log** (`[DirectSendCategoryWebhook]` tag, INFO level for
  `received` / `flagged` / `completed`):
  ```text
  [DirectSendCategoryWebhook] received: project_uuid=11111111-... app_uuid=22222222-... template_name=weni_order_invoiced template_category=MARKETING template_correct_category=MARKETING
  [DirectSendCategoryWebhook] flagged: project_uuid=11111111-... app_uuid=22222222-... template_name=weni_order_invoiced template_category=MARKETING template_correct_category=MARKETING integrated_agent_uuid=33333333-... template_uuid=44444444-... version_uuid=55555555-... previous_status=APPROVED new_status=FLAGGED reason=category_not_utility
  [DirectSendCategoryWebhook] completed: project_uuid=11111111-... app_uuid=22222222-... template_name=weni_order_invoiced templates_updated=1 integrated_agents_inspected=1
  ```

### Post-flight verification

Re-run the pre-flight shell snippet from §2. The output now reads:

```text
agent=33333333-... template=44444444-... version=55555555-... status=FLAGGED
```

This satisfies spec.md SC-001 ("the template's `current_version.status`
is `FLAGGED` within 1 second of the webhook returning HTTP 200").

---

## 4. Cross-feature verification: dispatch is skipped (US1 / SC-002)

Spec 002's dispatch gate
(`Broadcast.get_current_template` at
`retail/agents/domains/agent_webhook/services/broadcast.py:665-676`)
returns `None` for any `current_version.status != "APPROVED"` and
emits a `[BroadcastDispatch] skipped_due_to_status` audit-log line
with `version_status=FLAGGED`. To confirm:

1. Trigger an order-status event that would have matched the
   `weni_order_invoiced` template (e.g. a VTEX `payment-approved`
   webhook for an order in the named project).
2. Observe the broadcast log:
   ```text
   [BroadcastDispatch] skipped_due_to_status: project_uuid=11111111-... vtex_account=... template=weni_order_invoiced version_status=FLAGGED ...
   ```
3. Confirm zero new `BroadcastMessage` rows for the flagged
   template:
   ```sql
   SELECT COUNT(*)
     FROM broadcasts_broadcastmessage
    WHERE template_name = 'weni_order_invoiced'
      AND project_id = (SELECT id FROM projects_project WHERE uuid = '11111111-...')
      AND created_at > '<webhook fire timestamp>';
   ```
   Expected: `0`.

This satisfies spec.md SC-002 ("After a template is flagged by
this webhook, the next broadcast attempt against that template is
skipped 100% of the time").

---

## 5. Fire the webhook a second time — idempotent replay (US2 scenario 1)

Same `curl` command as §3. Expected:

- **HTTP status**: `200 OK`.
- **Response body**:
  ```json
  {
    "detail":                       "Already flagged.",
    "templates_updated":            0,
    "integrated_agents_inspected":  1
  }
  ```
- **Database side effect**: zero `UPDATE` statements (the
  early-return guard skips the write per FR-007c).
- **Audit log**:
  ```text
  [DirectSendCategoryWebhook] received: ...
  [DirectSendCategoryWebhook] flag_replay_noop: project_uuid=... app_uuid=... template_name=... template_category=MARKETING template_correct_category=MARKETING integrated_agent_uuid=... template_uuid=... version_uuid=... previous_status=FLAGGED
  [DirectSendCategoryWebhook] completed: ... templates_updated=0 integrated_agents_inspected=1
  ```

The `previous_status=FLAGGED` field on the `flag_replay_noop` line
is the operator-facing signal that the row was already in the
target state before the request. This satisfies spec.md SC-004
("when the same payload is replayed N times … the database
receives exactly one `UPDATE` against `Version.status`"). For the
bidirectional case — replays of a corrected-category payload
against the same `FLAGGED` Version, which auto-demote the Version
to `APPROVED` per FR-006c / FR-007d — see §5.1 below.

---

## 5.1 Fire the webhook with a corrected-category payload — auto-demote (US2 AS2 / FR-006c / FR-007d)

After §5 leaves the Version in `FLAGGED`, the operator fixes the
template content on the Meta side so Meta now classifies it as
`UTILITY`. Integrations re-fires the webhook with the corrected
payload:

```bash
curl -X POST "$BASE_URL/webhook/templates-status/api/category-notification/" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  --data-raw '{
    "project_uuid":              "11111111-1111-1111-1111-111111111111",
    "app_uuid":                  "22222222-2222-2222-2222-222222222222",
    "template_name":             "weni_order_invoiced",
    "template_category":         "UTILITY",
    "template_correct_category": "UTILITY"
  }'
```

### Expected outcome

- **HTTP status**: `200 OK`.
- **Response body**:
  ```json
  {
    "detail":                       "Auto-demoted.",
    "templates_updated":            1,
    "integrated_agents_inspected":  1
  }
  ```
- **Database side effect**: exactly one `UPDATE` against
  `templates_version.status` for the matched Version row; new
  value `"APPROVED"`. The Template's `current_version` FK is
  unchanged (FR-007a preserved on the demote branch).
- **Audit log** (INFO level for `received` / `auto_demoted` / `completed`):
  ```text
  [DirectSendCategoryWebhook] received: project_uuid=11111111-... app_uuid=22222222-... template_name=weni_order_invoiced template_category=UTILITY template_correct_category=UTILITY
  [DirectSendCategoryWebhook] auto_demoted: project_uuid=11111111-... app_uuid=22222222-... template_name=weni_order_invoiced template_category=UTILITY template_correct_category=UTILITY integrated_agent_uuid=33333333-... template_uuid=44444444-... version_uuid=55555555-... previous_status=FLAGGED new_status=APPROVED
  [DirectSendCategoryWebhook] completed: project_uuid=11111111-... app_uuid=22222222-... template_name=weni_order_invoiced templates_updated=1 integrated_agents_inspected=1
  ```

### Post-flight verification

Re-run the pre-flight shell snippet from §2. The output now reads:

```text
agent=33333333-... template=44444444-... version=55555555-... status=APPROVED
```

The dispatch gate from spec 002's `Broadcast.get_current_template`
immediately re-admits the template on the next order-status
broadcast attempt — no operator action required. Firing the same
`UTILITY/UTILITY` payload a third time (now against the
`APPROVED` Version) routes through the `no_action_required` path:
HTTP 200, `templates_updated=0`, `detail="No action required."`,
audit line `no_action_required`. This is the FR-008 last-clause
convergence behavior.

---

## 6. Operator-driven recovery channel (FR-014 second channel)

A `FLAGGED → APPROVED` demote has **two** supported channels per
FR-014: (a) the auto-demote channel walked through in §5.1
(`UTILITY/UTILITY` payload against a `FLAGGED` Version), and (b)
the operator-driven channel documented here. The operator channel
remains useful when the recovery is initiated by Retail's own
operator rather than by an upstream Meta-side determination — for
example, restoring a template that was manually `FLAGGED` via
`UpdateTemplateUseCase` for reasons unrelated to category
mismatch (per Assumption A11). The operator uses the existing
internal `update_template` endpoint to restore the template:

```bash
curl -X PATCH "$BASE_URL/api/templates/update/" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  --data-raw '{
    "version_uuid": "55555555-5555-5555-5555-555555555555",
    "status":       "APPROVED"
  }'
```

This routes through `UpdateTemplateUseCase`
(`retail/templates/usecases/update_template.py:46-64`) — the
existing operator-driven recovery channel pinned by FR-014.
Restoring `status=APPROVED` re-promotes the Version to
`Template.current_version` (existing behaviour from spec 002's
`UpdateTemplateUseCase`); the next dispatch attempt against the
restored template succeeds.

After restoration, post-flight verification re-runs the §2
snippet:

```text
agent=33333333-... template=44444444-... version=55555555-... status=APPROVED
```

---

## 7. Negative cases — confirm fail-closed behaviour (US3)

Each of the three negative cases below MUST return HTTP 200 with
the appropriate audit-log entry. No partial write happens; no
HTTP 5xx is returned (FR-004b, FR-005, FR-005a, FR-010b).

### 7.1 Misrouted `app_uuid` (US3 scenario 1)

```bash
curl -X POST "$BASE_URL/webhook/templates-status/api/category-notification/" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  --data-raw '{
    "project_uuid":              "11111111-1111-1111-1111-111111111111",
    "app_uuid":                  "00000000-0000-0000-0000-000000000000",
    "template_name":             "weni_order_invoiced",
    "template_category":         "MARKETING",
    "template_correct_category": "MARKETING"
  }'
```

Expected:

- **HTTP 200**, body
  `{"detail": "No matching IntegratedAgent.", "templates_updated": 0, "integrated_agents_inspected": 0}`.
- Audit log line:
  `[DirectSendCategoryWebhook] no_matching_integrated_agent: project_uuid=... app_uuid=00000000-... template_name=weni_order_invoiced template_category=MARKETING template_correct_category=MARKETING` (WARNING level per FR-009b).

### 7.2 Misrouted `template_name` (US3 scenario 2)

Same `(project, app_uuid)` as §3 but `template_name` set to a name
no Template on the matched IntegratedAgent owns
(e.g. `"weni_nonexistent"`).

Expected:

- **HTTP 200**, body
  `{"detail": "Template not found.", "templates_updated": 0, "integrated_agents_inspected": 1}`.
- Audit log lines:
  `[DirectSendCategoryWebhook] template_not_found: project_uuid=... app_uuid=... template_name=weni_nonexistent integrated_agent_uuid=...` (WARNING).

### 7.3 Malformed payload — missing field (Edge Case row 1)

```bash
curl -X POST "$BASE_URL/webhook/templates-status/api/category-notification/" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  --data-raw '{
    "project_uuid":      "11111111-1111-1111-1111-111111111111",
    "app_uuid":          "22222222-2222-2222-2222-222222222222",
    "template_name":     "weni_order_invoiced",
    "template_category": "MARKETING"
  }'
```

Expected:

- **HTTP 400**, body
  `{"template_correct_category": ["This field is required."]}`.
- No `[DirectSendCategoryWebhook]` audit-log entry (DRF's
  `django.request` logger handles the rejection per FR-010a /
  Edge Case row 1).

---

## 8. Cross-tenant isolation drill (SC-006)

To verify that the cross-tenant boundary holds, seed two projects
(A and B) such that project B's IntegratedAgent has a Version with
the same `app_uuid` as project A's `app_uuid`:

```bash
# Setup (one-off, run in the Django shell):
poetry run python manage.py shell <<'PY'
# ... seed project A's IntegratedAgent + Template + Version
# ... seed project B's IntegratedAgent + Template + Version using the SAME app_uuid value
PY

# Fire the webhook for project A:
curl -X POST "$BASE_URL/webhook/templates-status/api/category-notification/" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  --data-raw '{
    "project_uuid":              "<project A uuid>",
    "app_uuid":                  "<shared app uuid>",
    "template_name":             "weni_shared",
    "template_category":         "MARKETING",
    "template_correct_category": "MARKETING"
  }'
```

Expected:

- **HTTP 200**, body
  `{"detail": "Templates flagged.", "templates_updated": 1, "integrated_agents_inspected": 1}`.
- Project A's `Version.status` is `FLAGGED`.
- **Project B's `Version.status` is unchanged** (`APPROVED`).
- The `flagged` audit-log entry carries project A's
  `integrated_agent_uuid` / `template_uuid` / `version_uuid` —
  the audit log makes no reference to project B's IntegratedAgent.

This satisfies spec.md SC-006 ("in zero cases does a webhook for
project A flag a template owned by project B, even when the
`app_uuid` value coincidentally appears on a Version row in project
B").

---

## 9. Rollback

Rollback for this feature is non-destructive — the only
runtime-observable effect is the `FLAGGED` writes on
`Version.status` performed by webhook invocations between feature
deploy and feature revert. After a `git revert` of the feature PR:

1. The new URL entry
   (`templates-status/api/category-notification/`) is removed from
   `retail/webhooks/templates/urls.py`. Future POSTs return HTTP
   404 — Integrations is responsible for re-checking the endpoint
   availability before its next retry batch.
2. The `Version.status = "FLAGGED"` rows written between deploy and
   revert remain in the database. They are still effective at the
   dispatch gate (spec 002's `Broadcast.get_current_template` is
   not touched by this feature's revert). The operator may restore
   any of them to `APPROVED` via the existing internal
   `update_template` endpoint (see §6).
3. No new migration was applied (`data-model.md`), so no migration
   needs to be rolled back. The `templates.0017_alter_version_status_paused_flagged`
   migration from spec 002 is independent and stays.

**Operator-facing rollback procedure**:

```bash
# (1) Revert the feature PR
git revert <feature-PR-merge-sha>

# (2) Re-deploy
# (3) Optionally restore any FLAGGED templates that were flagged in error
#     via the existing PATCH /api/templates/update/ endpoint (one call per Version uuid)
```

No customer-visible message dispatch is affected by the rollback;
flagged templates remain flagged until manually restored, which is
the conservative and correct fail-safe behaviour for any
category-correctness signal that has been honoured.

---

## 10. Operational SQL parity checks

For post-deploy verification and ongoing operational confidence,
the following queries can be scheduled as periodic data-quality
checks. Any non-zero result is a candidate defect.

### 10.1 No FLAGGED Version without an audit-log trace

```sql
SELECT v.uuid, v.template_id, v.status, v.created_at
  FROM templates_version v
  JOIN templates_template t ON t.current_version_id = v.id
 WHERE v.status = 'FLAGGED'
   AND v.created_at > NOW() - INTERVAL '1 day'
 ORDER BY v.created_at DESC;
```

Every row in the result set MUST have a corresponding
`[DirectSendCategoryWebhook] flagged: ... version_uuid=<v.uuid>`
audit-log entry (or, less commonly, a manual operator-driven
`UpdateTemplateUseCase` invocation with `status="FLAGGED"`). A
`FLAGGED` row without a trace indicates either a third-party DB
write or an audit-log gap (Retail-side bug).

### 10.2 No cross-tenant flag leak

For any webhook invocation, the project boundary holds (SC-006):

```sql
SELECT v.uuid, v.project_id, t.integrated_agent_id, ia.project_id AS ia_project_id
  FROM templates_version v
  JOIN templates_template t ON t.current_version_id = v.id
  JOIN agents_integratedagent ia ON ia.uuid = t.integrated_agent_id
 WHERE v.status = 'FLAGGED'
   AND v.project_id != ia.project_id;
```

Expected: `0 rows`. A non-empty result indicates a tenant-isolation
violation — either an upstream IntegratedAgent re-assignment that
crossed projects, or a Retail-side bug that wrote `FLAGGED` to the
wrong row.

### 10.3 Counter parity between HTTP response and audit log

This is verified at the test level (`tasks.md` T019) rather than
at the SQL level — the counter values are not persisted, so the
SQL-level audit is not applicable. The test asserts that the same
two counters appear on (a) the HTTP 200 response body and (b) the
`completed` audit-log line for the same request.

---

## 11. Mapping back to spec

| Quickstart step           | Spec scenario                       | FR / SC                                |
| ------------------------- | ----------------------------------- | -------------------------------------- |
| §3 (flag firing)          | US1 scenario 1                      | FR-001, FR-006, FR-007, SC-001         |
| §4 (dispatch skipped)     | US1 + spec 002                      | FR-013, SC-002                         |
| §5 (flag replay)          | US2 scenario 1                      | FR-007c, FR-008, SC-004                |
| §5.1 (auto-demote replay) | US2 AS2                             | FR-006c, FR-007c, FR-007d, FR-008, FR-014 |
| §6 (operator restoration) | FR-014 operator-driven channel      | FR-014                                 |
| §7.1 (misrouted app)      | US3 scenario 1                      | FR-004, FR-004b, FR-009a               |
| §7.2 (misrouted template) | US3 scenario 2                      | FR-005                                 |
| §7.3 (malformed payload)  | Edge Case row 1                     | FR-003, FR-010a                        |
| §8 (cross-tenant drill)   | Edge Case row 9                     | FR-004, SC-006                         |
| §9 (rollback)             | Out-of-scope safety net             | (no FR — operator runbook)             |
| §10 (SQL parity checks)   | Out-of-band ops                     | SC-001, SC-005, SC-006                 |
