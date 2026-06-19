# Quickstart — WhatsApp Direct Send Broadcasts (OrderStatus)

**Feature**: `002-direct-send-broadcasts`
**Spec**: `./spec.md`
**Plan**: `./plan.md`

This is the operator / engineer "happy path" walkthrough that
validates the feature end-to-end against a real Direct Send-enabled
WhatsApp Cloud channel. Each step maps to one or more acceptance
scenarios from `spec.md`.

---

## 0. Prerequisites

| Item                                                                                            | Where it lives                                                              |
| ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| The OrderStatus agent has been pushed to the project (existing flow).                            | `POST /api/v3/agents/push/` (`PushAgentView`)                                |
| The project has a WhatsApp Cloud channel created via the existing onboarding flow.               | Integrations Engine — `apptype=wpp-cloud`                                    |
| The channel has been opted into the Direct Send Beta by Meta and Integrations has set            | Integrations DB — `App.config.direct_send = True`                            |
| `config.direct_send = True` on the channel-app.                                                  |                                                                             |
| The project's VTEX tenant has a resolvable `defaultLocale` (e.g. `pt-BR`, `es-MX`, `en-US`).      | VTEX IO `/api/tenant/tenants?q={vtex_account}`                               |
| `settings.ORDER_STATUS_AGENT_UUID` is set in the environment.                                    | `retail/settings.py:332`                                                     |
| Meta's library catalog has the OrderStatus templates available in the project's locale (or in `pt_BR` for the FR-003c fallback). | Meta library — read via `MetaClient.fetch_library_template_by_name_and_language` |

---

## 1. Run migrations

```bash
poetry run python manage.py migrate
```

**One** migration is applied:

- `templates.0017_alter_version_status_paused_flagged` — extends the
  `Version.status` enum with `PAUSED` and `FLAGGED`.

The Direct Send flag itself ships **no migration**: it is stored as
an optional key (`direct_send: bool`) inside the existing
`IntegratedAgent.config` JSONField, so legacy rows need no backfill
(absence of the key is interpreted as `False`). See `data-model.md §1`
for the canonical storage decision.

---

## 2. Assign the OrderStatus agent to a Direct Send-enabled project

```bash
curl -X POST "$BASE_URL/api/v3/agents/{order_status_agent_uuid}/assign/?app_uuid=<APP_UUID>&channel_uuid=<CHANNEL_UUID>" \
  -H "Authorization: Bearer $OIDC_TOKEN" \
  -H "Project-Uuid: <PROJECT_UUID>" \
  -H "Content-Type: application/json" \
  --data-raw '{
    "credentials": { ... },
    "include_templates": []
  }'
```

### Expected outcome (Story 2 scenario 1)

- HTTP 200 with the `ReadIntegratedAgentSerializer` body.
- The response body's `direct_send` field is `true`.
- One `IntegratedAgent` row, one `Credential` row per credential, and
  one `Template`+`Version` row per OrderStatus pre-approved template
  is persisted in a single atomic transaction.
- Each persisted `Template.metadata` carries the body, header,
  footer, buttons, language fetched from Meta's library catalog (in
  the project's resolved locale), plus the new `metadata.direct_send`
  observability sub-object.
- Each persisted `Version.status == "APPROVED"` (FR-004).
- **Zero** outgoing requests to:
  - the Integrations Engine `create_template`/`create_template_translation`/
    `create_library_template_message` endpoints (SC-003).
  - `MetaService.get_pre_approved_template` (the legacy push-time
    validation is not invoked because no Meta-side template
    creation happens).
- Logs include `[AssignAgent] integrated_agent created=...`
  followed by `[DirectSend] template_persisted: ...` for each
  template.

### Verification

```bash
poetry run python manage.py shell -c "
from retail.agents.domains.agent_integration.models import IntegratedAgent
ia = IntegratedAgent.objects.get(uuid='<from response>')
print('direct_send:', ia.config.get('direct_send', False))
for t in ia.templates.all():
    print(t.name, t.current_version.status, t.metadata.get('language'),
          t.metadata.get('direct_send'))
"
```

The flag is read from the `config` JSONField — direct attribute reads
(`ia.direct_send`) are forbidden because the field does not exist on
the model (`data-model.md §1`).

Expected:

```text
direct_send: True
weni_order_invoiced  APPROVED  pt_BR  {'fetched_from_meta_library': True, 'fetched_at': ..., 'requested_language': 'pt_BR', 'actual_language': 'pt_BR'}
weni_order_shipped   APPROVED  pt_BR  {'fetched_from_meta_library': True, 'fetched_at': ..., 'requested_language': 'pt_BR', 'actual_language': 'pt_BR'}
weni_order_delivered APPROVED  pt_BR  {'fetched_from_meta_library': True, 'fetched_at': ..., 'requested_language': 'pt_BR', 'actual_language': 'pt_BR'}
weni_order_canceled  APPROVED  pt_BR  {'fetched_from_meta_library': True, 'fetched_at': ..., 'requested_language': 'pt_BR', 'actual_language': 'pt_BR'}
```

---

## 3. Trigger an order-status broadcast through Direct Send

Fire a VTEX order-status webhook (the existing entry point at
`retail/webhooks/vtex/...`) for a contact in the project:

```bash
curl -X POST "$BASE_URL/api/v3/webhooks/vtex/order-status/" \
  -H "Content-Type: application/json" \
  --data-raw '{
    "Domain":    "Marketplace",
    "OrderId":   "12345-01",
    "State":     "invoiced",
    "LastState": "ready-for-handling",
    "Origin":    {"Account": "<vtex_account>", "Sender": "order-status-api"}
  }'
```

### Expected outcome (Story 1 acceptance scenarios)

The local `Template.metadata.body` (persisted in §2 from Meta's library catalog) carries the un-substituted source text:

```text
"Olá {{1}}, sua nota fiscal do pedido {{2}} foi emitida."
```

The Lambda returns the variable values for the substitution:

```jsonc
{
  "template": "weni_order_invoiced",
  "template_variables": { "1": "Maria", "2": "12345" },
  "contact_urn": "whatsapp:5598123456789",
  "status": 0
}
```

Retail substitutes `{{1}}` → `"Maria"` and `{{2}}` → `"12345"` server-side and sends the fully-substituted body to Flows:

```jsonc
{
  "project": "<PROJECT_UUID>",
  "urns":    ["whatsapp:5598123456789"],
  "channel": "<CHANNEL_UUID>",
  "msg": {
    "direct_send": true,
    "category":    "utility",
    "direct_send_template_name": "weni_order_invoiced",
    "text":        "Olá Maria, sua nota fiscal do pedido 12345 foi emitida."
  }
}
```

> **⚠️ FR-014c / FR-014d wire-shape notes** — on the Direct Send
> path, the local template name lives on the top-level sibling key
> `msg.direct_send_template_name` (FR-014c(g)); locale is computed
> internally for `BroadcastMessage` persistence and datalake events
> but is intentionally absent from the wire (FR-014c(f)); the
> substituted body is emitted as `msg.text` (FR-014d) — the
> internal storage key `Template.metadata.body` is preserved
> unchanged (FR-014d(c)). See
> `contracts/messaging-gateway-payload.md §3.1` for the canonical
> wire contract.

Verify by inspecting Flows' inbound logs (or by mocking the Flows
service in a local run; see §6).

A `BroadcastMessage` row is persisted (FR-016, SC-005). Verify:

```bash
poetry run python manage.py shell -c "
from retail.broadcasts.models import BroadcastMessage
last = BroadcastMessage.objects.order_by('-created_at').first()
print(last.template_name, last.template_version, last.contact_urn, last.status)
"
```

---

## 4. Variable substitution edge cases (Story 1)

### 4.1 Body with no variables

Push the OrderStatus agent with a template whose body contains no
`{{N}}` placeholders. Trigger the webhook. Verify Flows receives
the literal body text — no warnings logged.

### 4.2 Variable indices missing from the rule engine output

Lambda returns `{"1": "Maria"}` for a template body
`"Olá {{1}}, seu pedido {{2}} foi enviado."`. Verify:

- The dispatched `body` is `"Olá Maria, seu pedido  foi enviado."`
  (empty string for the missing index).
- A WARNING log is emitted: `variable_missing: template_name=...
  index=2`.
- `BroadcastMessage` is persisted normally.

### 4.3 Image header + CTA URL button

With a template that has an image header and a CTA URL button, fire
the webhook with Lambda payload that includes
`{"image_url": "https://...", "button": "12345"}`. Verify:

- `msg.header.type == "image"` and `msg.header.image_url` is the
  literal URL.
- `msg.attachments[0]` is `"image/jpeg:<URL>"`.
- `msg.interaction_type == "cta_url"` (FR-014a; spelling
  `interactive_type` is INVALID).
- `msg.cta_message == {"display_text": "<substituted button label>",
  "url": "https://loja.com/track/12345"}` (FR-014a; the URL is the
  final substituted form).
- `msg.buttons` is **absent** — the Direct Send path NEVER emits
  `msg.buttons` (FR-014a(b) + FR-014b(b); the key is LEGACY-ONLY).
- If the same template also carries `QUICK_REPLY` buttons,
  `msg.quick_replies` is a flat array of post-substitution title
  strings (FR-014b); cardinality 1..3.

> **Historical note (pre-FR-014a / FR-014b — Session 2026-05-22 Q4 /
> Q10)**: earlier revisions of this script asserted
> `msg.buttons[0] == {"sub_type": "cta_url", "display_text": "...",
> "url": "..."}` and a sibling `{"sub_type": "reply", "id", "title"}`
> shape for QUICK_REPLY. Both are documentation/implementation
> errors per spec FR-014a(b) / FR-014b(b); the canonical wire shape
> is restated above. The pre-FR-014a/b code paths are tracked as
> SUPERSEDED in `tasks.md` (T011a `[~]`, T013 overlay note) and are
> being relocated by Phase 8 / T113 / T114.

---

## 5. PAUSED / FLAGGED status (Story 3)

### 5.1 Skip on PAUSED

Manually transition the current Version of a template to `PAUSED`:

```bash
poetry run python manage.py shell -c "
from retail.templates.models import Version
v = Version.objects.get(template__name='weni_order_invoiced',
                        template__integrated_agent__uuid='<IA_UUID>')
v.status = 'PAUSED'
v.save(update_fields=['status'])
"
```

Fire the order-status webhook again. Expected:

- No request reaches Flows.
- No `BroadcastMessage` row is persisted.
- An audit log entry includes `template_name=weni_order_invoiced
  version_status=PAUSED order_id=12345-01`.

### 5.2 Skip on FLAGGED

Same as 5.1 with `v.status = "FLAGGED"`.

### 5.3 Resume on APPROVED

Set `v.status = "APPROVED"` again. Fire the webhook. Verify the
broadcast is dispatched normally (Story 3 scenario 3, SC-006).

### 5.4 Set PAUSED / FLAGGED via the `update_template` endpoint (FR-026)

The shell hacks in §5.1 / §5.2 bypass the production write path. To
exercise the canonical FR-026 contract end-to-end — the
`update_template` endpoint accepts `PAUSED` and `FLAGGED` as valid
`status` values and persists them as-is **without** triggering the
`current_version` promotion logic that runs only on `APPROVED` — POST
the new status through the endpoint:

```bash
curl -X PATCH "$BASE_URL/api/v2/templates/<TEMPLATE_UUID>/" \
  -H "Authorization: Bearer $OIDC_TOKEN" \
  -H "Content-Type: application/json" \
  --data-raw '{
    "version_uuid": "<VERSION_UUID>",
    "status":       "PAUSED"
  }'
```

Expected:

- HTTP 200.
- `Version.status == "PAUSED"` (read back from the DB).
- `Template.current_version` is **unchanged** (the APPROVED-only
  promotion branch did NOT fire). Verify with:

  ```bash
  poetry run python manage.py shell -c "
  from retail.templates.models import Template, Version
  t = Template.objects.get(uuid='<TEMPLATE_UUID>')
  v = Version.objects.get(uuid='<VERSION_UUID>')
  print('version_status:', v.status)
  print('current_version_uuid:', t.current_version.uuid if t.current_version else None)
  "
  ```

- The next order-status webhook for the same template is skipped by
  the PAUSED/FLAGGED dispatch gate (FR-012) — same observable as §5.1.

Repeat with `"status": "FLAGGED"` to exercise the symmetric path.

---

## 6. Legacy path regression test (Story 4)

### 6.1 Direct Send disabled at the channel

Repeat §2 against a project whose `App.config.direct_send` is
`false` (or absent). Expected:

- `ia.config.get("direct_send", False) == False` (the key is absent
  from `config` on the persisted IntegratedAgent — legacy behaviour).
- The existing `_create_library_templates` flow runs:
  `CreateLibraryTemplateUseCase.execute` then `notify_integrations`
  (the integrations-engine submission), exactly as today.
- No call to `MetaService.fetch_library_template_by_name_and_language`.

### 6.2 Channel lookup fails

Repeat §2 against a project whose `App.config.direct_send` cannot
be retrieved (e.g. Integrations returns 5xx). Expected:

- `ia.config.get("direct_send", False) == False` (the key is absent
  from `config` because `_resolve_direct_send_flag` returns `False`
  on lookup failure and the assignment never writes the key).
- A WARNING log: `[DirectSend] channel_lookup_failed: agent=... app_uuid=...`.
- Behavior matches §6.1 — full legacy path.

### 6.3 Legacy dispatch payload byte-parity

Fire the same VTEX webhook used in §3 against a Direct Send-DISABLED
IntegratedAgent. Capture the JSON sent to Flows. It MUST be
byte-identical to the payload Retail produces today (FR-015,
SC-004). The recommended way to enforce this is a snapshot test in
`retail/agents/tests/services/test_broadcast_legacy_payload.py`
that pins the legacy shape.

---

## 7. Atomic assignment failure (FR-003d, Story 2 scenario 5)

Make Meta's library catalog return empty for a required template
(e.g. delete the template from the catalog or simulate a 5xx by
patching `MetaService.fetch_library_template_by_name_and_language`
in a local test). Run the assignment.

Expected:

- HTTP 4xx with a body identifying the failed template (e.g.
  `{"detail": "Template weni_order_shipped is not available in
  pt_BR or fallback locale", "code": "direct_send_template_unavailable"}`).
- Zero rows of `IntegratedAgent`, `Template`, `Version`, `Credential`
  persisted (the use case is `@transaction.atomic`).
- Logs include `[DirectSend] assignment_failed_atomic: ...`.

---

## 8. Test commands (CI parity)

```bash
poetry run coverage run manage.py test retail/agents retail/templates retail/broadcasts retail/services/meta retail/services/integrations
poetry run coverage report -m | tail -40
poetry run python contrib/compare_coverage.py
```

The third command MUST NOT report `Number of test lines decreased`.
Pre-commit hooks (Black + flake8) must pass on every changed file.

---

## 9. Rollback

If a regression is detected after release:

1. Disable Direct Send on the affected project's WhatsApp channel
   in Integrations (set `config.direct_send=false`).
2. Re-assign the OrderStatus agent on the affected project. The
   re-assignment writes `agent.config["direct_send"] = False` and
   restores the legacy path on the next broadcast. The persisted
   Direct Send templates remain in the database (harmless) and can
   be cleaned up by the existing template-deletion flows.

**Migration rollback**: the only migration this feature ships is
`templates.0017_alter_version_status_paused_flagged` (additive enum
extension). Reverting it with
`poetry run python manage.py migrate templates <previous>` is safe
but not required — once the dispatch-gate code is removed, the new
enum values stay unused. Reverting only the feature code while
leaving the migration applied is also safe.

The Direct Send flag itself adds **no schema** to `IntegratedAgent`
(it lives inside the existing `config` JSON, per `data-model.md §1`),
so there is no agents-side migration to revert. Once the feature
code is removed, the orphaned `config["direct_send"]` key on any
in-flight assignment is silently ignored — `obj.config.get(...)` in
reverted code that no longer reads it has no effect.

---

## 10. Post-deploy exactly-once parity checks (SC-009)

After a baseline batch has been replayed through staging or
production, the five Retail-internal exactly-once invariants
(spec §SC-009) MUST hold. Each invariant is expressed as a
runnable SQL check; any non-zero result is a candidate defect
that should be linked back to the originating deployment window.

The five checks are non-destructive and can be scheduled as part
of a periodic data-quality job. Schema details (exact table /
column names) should be reconciled against the live `\dt` output
before adopting; the invariant statements above are authoritative,
the SQL below is illustrative.

### 10.1 At-most-one-broadcast-per-canonical-tuple (FR-028)

`BroadcastMessage` does NOT persist `current_state` — the fourth
component of the canonical idempotency tuple is captured ONLY in
the `[ORDER_STATUS] executing` / `[ORDER_STATUS] duplicate_skipped`
audit log lines. The **canonical** SC-009(a) verification is therefore
a log diff:

```text
count([ORDER_STATUS] executing lines for a given window)
  == count(BroadcastMessage rows whose created_at falls in that window)
```

The persisted-data check below is a **weaker corollary** that runs
purely against the database and catches the most common dedup
regressions (a worker bypassing `_is_duplicate_event`, the cache key
losing a component, etc.). It groups by
`(project_id, integrated_agent_id, order_id, template_name)` — using
`template_name` as a proxy for `current_state`, because the Lambda
maps `current_state` → `template` deterministically per Spec
Assumption "Lambda deterministic output". A false positive is
theoretically possible when an operator misconfigures the rule
engine so that two distinct `current_state` values resolve to the
same `template` (spec Edge Case "Lambda returns the SAME `template`
name for two distinct `current_state` values"); cross-check the
audit log to confirm.

```sql
-- Returns 0 rows if the corollary holds.
-- Replace 60 with the live ORDER_STATUS_DUPLICATE_WINDOW_SECONDS value.
SELECT
    ia.project_id,
    bm.integrated_agent_id,
    bm.order_id,
    bm.template_name,
    COUNT(*)             AS broadcast_count,
    MIN(bm.created_at)   AS first_seen,
    MAX(bm.created_at)   AS last_seen
FROM broadcasts_broadcastmessage bm
JOIN agents_integratedagent ia ON ia.id = bm.integrated_agent_id
WHERE bm.created_at >= NOW() - INTERVAL '1 hour'
GROUP BY ia.project_id, bm.integrated_agent_id, bm.order_id, bm.template_name
HAVING COUNT(*) > 1
   AND MAX(bm.created_at) - MIN(bm.created_at) < INTERVAL '60 seconds';
```

### 10.2 broadcast_id 1:1 with BroadcastMessage (FR-032)

```sql
SELECT
    (SELECT COUNT(DISTINCT broadcast_id) FROM broadcasts_broadcastmessage WHERE broadcast_id IS NOT NULL) AS distinct_ids,
    (SELECT COUNT(*) FROM broadcasts_broadcastmessage WHERE broadcast_id IS NOT NULL) AS row_count;
-- distinct_ids MUST EQUAL row_count.
```

### 10.3 external_message_id 1:1 with BroadcastMessage (FR-032)

```sql
SELECT
    (SELECT COUNT(DISTINCT external_message_id) FROM broadcasts_broadcastmessage WHERE external_message_id IS NOT NULL) AS distinct_ids,
    (SELECT COUNT(*) FROM broadcasts_broadcastmessage WHERE external_message_id IS NOT NULL) AS row_count;
-- distinct_ids MUST EQUAL row_count.
```

### 10.4 BroadcastConversion 1:1 with (project, order_id) (FR-033)

```sql
SELECT project_id, order_id, COUNT(*)
FROM broadcasts_broadcastconversion
GROUP BY project_id, order_id
HAVING COUNT(*) > 1;
-- MUST return 0 rows.
```

### 10.5 broadcasts_delivered counter parity (FR-034)

The counter is incremented on the FIRST `DELIVERED` transition only
(FR-034). Counting rows whose current `status` is in `{DELIVERED,
READ}` is valid because FR-035's lifecycle-rank guard rejects
backward transitions, so every row currently in `READ` was counted
once at its prior `DELIVERED` transition — see spec SC-009(e) for
the full rationale. If a future change relaxes the lifecycle-rank
guard so that `READ` can be reached without a prior `DELIVERED`,
this check MUST be reformulated against `previous_status` transition
history.

```sql
-- After a quiescent period, the counter MUST equal the count of
-- DELIVERED/READ messages for each IntegratedAgent.
SELECT
    ia.uuid,
    ia.broadcasts_delivered AS counter,
    COUNT(bm.id) FILTER (WHERE bm.status IN ('DELIVERED', 'READ')) AS observed
FROM agents_integratedagent ia
LEFT JOIN broadcasts_broadcastmessage bm ON bm.integrated_agent_id = ia.id
GROUP BY ia.uuid, ia.broadcasts_delivered
HAVING ia.broadcasts_delivered <> COUNT(bm.id) FILTER (WHERE bm.status IN ('DELIVERED', 'READ'));
-- MUST return 0 rows once the topic queue is drained.
```
