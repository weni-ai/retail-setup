# Quickstart — Template Sample Validation Endpoint for Direct Send

**Feature**: `004-template-sample-validation`
**Spec**: `./spec.md`
**Plan**: `./plan.md`

This is the operator / engineer "happy path" walkthrough that
validates the feature end-to-end against a real Direct Send-enabled
WhatsApp Cloud channel. Each step maps to one or more acceptance
scenarios from `spec.md`.

---

## 0. Prerequisites

| Item                                                                                            | Where it lives                                                                                  |
| ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Spec 002 (`002-direct-send-broadcasts`) is deployed.                                            | The `direct_send` flag + `Broadcast.build_direct_send_message` dispatch path live in spec 002.  |
| Spec 003 (`003-template-category-webhook`) is deployed.                                         | Not strictly required, but the audit-log pattern (`[TAG] event_name: k=v`) follows that precedent. |
| The OrderStatus agent has been pushed and assigned to the project (existing flow).              | `POST /api/v3/agents/push/` + `POST /api/v3/agents/{uuid}/assign/`                              |
| The project has a WhatsApp Cloud channel created via the existing onboarding flow.              | Integrations Engine — `apptype=wpp-cloud`                                                       |
| The channel has been opted into the Direct Send Beta and `IntegratedAgent.config["direct_send"] == True` was written at assignment time. | `AssignAgentUseCase` — `retail/agents/domains/agent_integration/usecases/assign.py:162`         |
| The project's wpp-cloud channel-app is reachable via `IntegrationsService.get_channel_app("wpp-cloud", app_uuid)` and the returned dict carries a non-empty `config["waba"]["id"]`. | Integrations Engine — same path `ConfigureOneClickPaymentUseCase._fetch_channel_info` consumes at `retail/projects/usecases/configure_one_click_payment.py:192`. |
| At least one local `Template` exists on the assigned IntegratedAgent with                       | `retail/templates/models.py` — created at assignment time by                                    |
| `current_version.status = "APPROVED"` and at least one `Version` carrying                       | `AssignAgentUseCase._create_library_templates`                                                  |
| `integrations_app_uuid` equal to the channel's `app_uuid`.                                       |                                                                                                  |
| A user / service-account exists with the `IsAuthenticated` JWT and `HasProjectPermission`       | Same JWT the legacy `PATCH /api/v3/templates/<uuid>/` endpoint accepts; granted via Connect API. |
| (contributor / moderator role per `retail.internal.permissions.HasProjectPermission`).          |                                                                                                  |
| Meta WABA is opted into the Direct Send Beta and the `Sample API` is unblocked (no              | Coordinate with `wadirectsendapisupport@meta.com` if you see error `2388341`.                   |
| `2388341 — Samples API Access is restricted` error returned).                                    |                                                                                                  |

---

## 1. Run migrations

```bash
poetry run python manage.py migrate
```

**Zero** new migrations are applied — this feature ships no schema
change (spec.md A10 / FR-010, `data-model.md`). The pre-existing
spec 002 migration `templates.0017_alter_version_status_paused_flagged`
provides the `FLAGGED` value (unused by this feature but required by
spec 003 if deployed), and the long-standing `APPROVED` /
`PENDING` values cover this feature's needs.

---

## 2. Pre-flight: capture the baseline Template state

Before firing the new endpoint, snapshot the template:

```bash
poetry run python manage.py shell <<'PY'
from retail.templates.models import Template

template = Template.objects.select_related("integrated_agent").get(
    uuid="0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11"
)

print("template.metadata.body:", template.metadata.get("body"))
print("template.current_version.uuid:", template.current_version.uuid)
print("template.current_version.template_name:", template.current_version.template_name)
print("template.current_version.status:", template.current_version.status)
print("template.integrated_agent.config['direct_send']:",
      template.integrated_agent.config.get("direct_send", False))
PY
```

Expected output:

```text
template.metadata.body: Olá {{1}}, seu pedido foi confirmado
template.current_version.uuid: <some uuid>
template.current_version.template_name: weni_order_confirmed_<original_timestamp>
template.current_version.status: APPROVED
template.integrated_agent.config['direct_send']: True
```

`direct_send=True` confirms the template is eligible for the new
endpoint per FR-002a. If it's `False` or absent, the endpoint will
refuse with HTTP 400 / `not_direct_send_eligible`.

---

## 3. Happy path — submit a UTILITY-classifying sample

The new endpoint accepts the same body shape as the legacy
`PATCH /api/v3/templates/<uuid>/` (per FR-014 / US4) plus the
length-cap validations from FR-003a. Fire the sample for a body
edit Meta will classify as UTILITY:

```bash
curl -X POST \
  -H "Authorization: Bearer ${JWT}" \
  -H "Project-Uuid: 11111111-2222-3333-4444-555566667777" \
  -H "Content-Type: application/json" \
  -d '{
    "template_body": "Olá {{1}}, seu pedido #{{2}} foi enviado e chega em até 3 dias úteis.",
    "template_body_params": ["João", "1234"],
    "app_uuid": "a1b2c3d4-1111-2222-3333-444455556666",
    "project_uuid": "11111111-2222-3333-4444-555566667777",
    "language": "pt_BR"
  }' \
  "https://retail.example.com/api/v3/templates/0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11/sample/"
```

Expected HTTP 200 response (US1 AS1):

```jsonc
{
  "category": "UTILITY",
  "template_updated": true,
  "meta_sample_response": { "success": true, "category": "UTILITY" },
  "template": {
    "uuid": "0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11",
    "status": "APPROVED",                                                              // ← per FR-006d, not PENDING
    "metadata": {
      "body": "Olá {{1}}, seu pedido #{{2}} foi enviado e chega em até 3 dias úteis.", // ← raw {{N}} preserved per A7
      "body_params": ["João", "1234"],
      "header": null,
      "footer": null,
      "buttons": null,
      "category": "UTILITY",
      "language": "pt_BR"
    },
    "name": "weni_order_confirmed",
    // ... other ReadTemplateSerializer fields
  }
}
```

Key invariants to verify:

- `category` = `"UTILITY"` and `template_updated` = `true`.
- `template.status` = `"APPROVED"` (NOT `"PENDING"`) per FR-006d.
- `template.metadata.body` retains `{{1}}` / `{{2}}` placeholders
  (NOT the substituted strings) per A7.
- `Template.current_version` was advanced to a new Version row.

Verify the persisted state:

```bash
poetry run python manage.py shell <<'PY'
from retail.templates.models import Template

template = Template.objects.select_related("current_version").get(
    uuid="0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11"
)

# Should be the NEW version's uuid (different from the baseline)
print("template.current_version.uuid:", template.current_version.uuid)
# Should be a fresh weni_<name>_<new_timestamp>
print("template.current_version.template_name:", template.current_version.template_name)
# Should be "APPROVED"
print("template.current_version.status:", template.current_version.status)
# Should be the new body with raw {{N}} placeholders preserved
print("template.metadata.body:", template.metadata.get("body"))

# The previous current_version row should still exist in the versions history
print("Total versions:", template.versions.count())
PY
```

Verify the audit log (search for `[TemplateSampleValidation]` in
your log infrastructure):

```text
[TemplateSampleValidation] received: project_uuid=11111111-... app_uuid=a1b2c3d4-... template_uuid=0fa1c8e2-... template_body_len=70 template_header_present=false template_footer_present=false buttons_count=0
[TemplateSampleValidation] meta_sample_submitted: waba_id=<waba_id> template_uuid=0fa1c8e2-... sample_type=text
[TemplateSampleValidation] meta_sample_response: template_uuid=0fa1c8e2-... category=UTILITY success=true http_status=200
[TemplateSampleValidation] template_updated: template_uuid=0fa1c8e2-... new_version_uuid=<new_uuid> new_version_status=APPROVED previous_current_version_uuid=<old_uuid> previous_current_version_status=APPROVED
```

Note that customer-facing content (`template_body`) is logged as
`template_body_len=70` (length only) per FR-008c, not verbatim.

This validates US1 AS1 + SC-001 + SC-005 + SC-007.

---

## 4. Verify Direct Send dispatch sees the new content immediately

Per SC-004 the next Direct Send broadcast against this template
should render the NEW content with no cache lag, no asynchronous
convergence window.

Trigger a synthetic broadcast through the existing order-status
dispatch path (or simulate it from `manage.py shell`):

```bash
poetry run python manage.py shell <<'PY'
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.services.broadcast import Broadcast
from retail.templates.models import Template

template = Template.objects.select_related(
    "current_version", "integrated_agent"
).get(uuid="0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11")

integrated_agent = template.integrated_agent

broadcast = Broadcast()
message = broadcast.build_direct_send_message(
    data={
        "contact_urn": "whatsapp:+5511999999999",
        "template_variables": {"1": "Maria", "2": "5678"},
    },
    channel_uuid=str(integrated_agent.channel_uuid),
    project_uuid=str(integrated_agent.project.uuid),
    template=template,
    integrated_agent=integrated_agent,
)

print("msg.direct_send_template_name:", message["msg"]["direct_send_template_name"])
print("msg.text:", message["msg"]["text"])
PY
```

Expected output:

```text
msg.direct_send_template_name: weni_order_confirmed_<NEW_timestamp>
msg.text: Olá Maria, seu pedido #5678 foi enviado e chega em até 3 dias úteis.
```

Two things to verify:

- `direct_send_template_name` is the NEW Version's `template_name`
  (not the baseline's). This confirms `Template.current_version`
  was advanced in-line per FR-006d.
- `msg.text` is the NEW body with the DISPATCH-time variables
  substituted (`Maria`, `5678`), NOT the sample-time variables
  (`João`, `1234`). This confirms A7's "outbound substitution is
  per-call, persisted metadata keeps raw `{{N}}`" guarantee.

This validates US2 + SC-004.

---

## 5. Non-UTILITY path — submit a MARKETING-classifying sample

Fire a sample for content Meta will classify as MARKETING:

```bash
curl -X POST \
  -H "Authorization: Bearer ${JWT}" \
  -H "Project-Uuid: 11111111-2222-3333-4444-555566667777" \
  -H "Content-Type: application/json" \
  -d '{
    "template_body": "🔥 50% OFF em todos os produtos só este final de semana! Compre agora.",
    "app_uuid": "a1b2c3d4-1111-2222-3333-444455556666",
    "project_uuid": "11111111-2222-3333-4444-555566667777"
  }' \
  "https://retail.example.com/api/v3/templates/0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11/sample/"
```

Expected HTTP 200 response (US1 AS2):

```jsonc
{
  "category": "MARKETING",
  "template_updated": false,
  "meta_sample_response": { "success": true, "category": "MARKETING" },
  "template": {
    "uuid": "0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11",
    "status": "APPROVED",
    "metadata": {
      "body": "Olá {{1}}, seu pedido #{{2}} foi enviado e chega em até 3 dias úteis.",
      // ... UNCHANGED from the step 3 happy path
    }
  }
}
```

Verify the persisted state is UNCHANGED from step 3:

```bash
poetry run python manage.py shell <<'PY'
from retail.templates.models import Template

template = Template.objects.select_related("current_version").get(
    uuid="0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11"
)

# Should still be the UTILITY-submitted version, not a new one
print("template.metadata.body:", template.metadata.get("body"))
print("template.current_version.template_name:", template.current_version.template_name)
PY
```

Verify the audit log shows the `update_skipped` event:

```text
[TemplateSampleValidation] received: project_uuid=11111111-... app_uuid=a1b2c3d4-... template_uuid=0fa1c8e2-... template_body_len=68 ...
[TemplateSampleValidation] meta_sample_submitted: waba_id=<waba_id> template_uuid=0fa1c8e2-... sample_type=text
[TemplateSampleValidation] meta_sample_response: template_uuid=0fa1c8e2-... category=MARKETING success=true http_status=200
[TemplateSampleValidation] update_skipped: template_uuid=0fa1c8e2-... category=MARKETING
```

This validates US1 AS2 + SC-002.

---

## 6. Direct-Send-ineligibility refusal (HTTP 400)

Pick a Template whose `integrated_agent.config["direct_send"]` is
absent / `False` (e.g. a legacy assignment before the Direct Send
rollout):

```bash
curl -X POST \
  -H "Authorization: Bearer ${JWT}" \
  -H "Project-Uuid: 11111111-2222-3333-4444-555566667777" \
  -H "Content-Type: application/json" \
  -d '{
    "template_body": "Some body",
    "app_uuid": "a1b2c3d4-...",
    "project_uuid": "11111111-..."
  }' \
  "https://retail.example.com/api/v3/templates/<legacy_template_uuid>/sample/"
```

Expected HTTP 400 response (US3 AS4):

```jsonc
{
  "detail": "Template is not Direct Send-eligible",
  "error_code": "not_direct_send_eligible"
}
```

Verify NO Meta sample call was made (no
`meta_sample_submitted` audit line) and NO local mutation
occurred. The audit log shows:

```text
[TemplateSampleValidation] received: project_uuid=11111111-... template_uuid=<legacy_template_uuid> ...
[TemplateSampleValidation] not_direct_send_eligible: template_uuid=<legacy_template_uuid> integrated_agent_uuid=<uuid_or_null> direct_send_flag=False
```

This validates FR-002a + FR-007e + US3 AS4.

---

## 7. WABA-not-configured refusal (HTTP 400)

Per the 2026-05-26 clarification, this endpoint resolves the WABA
id via a live call to
`IntegrationsService.get_channel_app("wpp-cloud", app_uuid)`. All
three failure modes (integrations infra failure, no app for the
supplied `app_uuid`, app exists but `config["waba"]["id"]` is
missing / empty) collapse to one user-facing HTTP 400 response;
the audit log discriminates via `integrations_response_present`.

The cleanest way to exercise this path is to submit an `app_uuid`
the integrations engine does not recognize:

```bash
curl -X POST \
  -H "Authorization: Bearer ${JWT}" \
  -H "Project-Uuid: 11111111-2222-3333-4444-555566667777" \
  -H "Content-Type: application/json" \
  -d '{
    "template_body": "Hello {{1}}",
    "app_uuid": "00000000-0000-0000-0000-000000000000",
    "project_uuid": "11111111-2222-3333-4444-555566667777"
  }' \
  "https://retail.example.com/api/v3/templates/<uuid>/sample/"
```

To exercise the "app exists but config missing `waba_id`" mode in
a test environment, mock `IntegrationsService.get_channel_app` to
return a dict with no `waba` key:

```bash
poetry run python manage.py shell <<'PY'
from unittest.mock import patch
from django.test import Client

with patch(
    "retail.templates.usecases.validate_template_sample"
    ".IntegrationsService.get_channel_app",
    return_value={"config": {}},   # no waba sub-key
):
    response = Client().post(
        "/api/v3/templates/<uuid>/sample/",
        data={
            "template_body": "Hello {{1}}",
            "app_uuid": "<any-uuid>",
            "project_uuid": "11111111-...",
        },
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer <JWT>",
        HTTP_PROJECT_UUID="11111111-...",
    )
    print(response.status_code, response.json())
PY
```

Expected HTTP 400 response (US3 AS3):

```jsonc
{
  "detail": "WABA not configured for this project",
  "error_code": "waba_not_configured"
}
```

The audit log shows the new payload per FR-008a — the
`integrations_response_present` flag separates "service down /
unknown `app_uuid`" (`false`) from "app exists but unconfigured"
(`true`):

```text
[TemplateSampleValidation] received: project_uuid=11111111-... app_uuid=00000000-... template_uuid=<uuid> ...
[TemplateSampleValidation] waba_not_configured: project_uuid=11111111-... app_uuid=00000000-... integrations_response_present=false
```

For the "app exists but unconfigured" path, expect
`integrations_response_present=true` on the same event token.

This validates FR-005a + FR-007d + FR-008a + US3 AS3.

---

## 8. Meta-side failure simulation (HTTP 502)

Simulate a `CustomAPIException` by pointing `META_API_URL` to an
unreachable host in a test environment:

```bash
META_API_URL=https://localhost:9999 poetry run python manage.py runserver
```

Fire the endpoint:

```bash
curl -X POST -H "..." -d '{ "template_body": "...", ... }' \
  "http://localhost:8000/api/v3/templates/<uuid>/sample/"
```

Expected HTTP 502 response (US3 AS1 / FR-007b):

```jsonc
{
  "detail": "Meta sample submission failed",
  "error_code": "meta_unavailable",
  "meta_response": {
    "error": {
      "message": "Connection refused",
      "type": "ConnectionError"
    }
  }
}
```

The audit log shows (with `exc_info=True`):

```text
[TemplateSampleValidation] received: ...
[TemplateSampleValidation] meta_sample_submitted: ...
[TemplateSampleValidation] meta_error: template_uuid=<uuid> exception_class=CustomAPIException http_status=503 meta_error_code=null
Traceback (most recent call last):
  ...
```

This validates FR-005c + FR-007b + US3 AS1.

---

## 9. FLAGGED-template recovery via UTILITY sample

Spec 003 may have flagged a template via the
`template_correct_category_detection` webhook
(`Version.status = "FLAGGED"`). The new endpoint is a third
recovery channel (spec.md Edge Case for FLAGGED templates).

Set up a flagged template:

```bash
poetry run python manage.py shell <<'PY'
from retail.templates.models import Template

template = Template.objects.select_related("current_version").get(
    uuid="0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11"
)
template.current_version.status = "FLAGGED"
template.current_version.save(update_fields=["status"])
print("Status now:", template.current_version.status)
PY
```

Fire the endpoint with content that will classify as UTILITY:

```bash
curl -X POST -H "..." -d '{
    "template_body": "Olá {{1}}, sua entrega está a caminho!",
    "template_body_params": ["João"],
    "app_uuid": "a1b2c3d4-...",
    "project_uuid": "11111111-..."
  }' \
  "https://retail.example.com/api/v3/templates/0fa1c8e2-.../sample/"
```

Expected HTTP 200 response — `template.status` becomes
`"APPROVED"` (the new Version is APPROVED + current_version is
repointed to it). The previously-FLAGGED Version remains in the
versions history but is no longer current. The next Direct Send
dispatch reads the new APPROVED Version and broadcasts the new
content.

The audit log's `template_updated` event carries the recovery
signal:

```text
[TemplateSampleValidation] template_updated: template_uuid=0fa1c8e2-... new_version_uuid=<new> new_version_status=APPROVED previous_current_version_uuid=<flagged_uuid> previous_current_version_status=FLAGGED
```

`previous_current_version_status=FLAGGED` is the operator-facing
signal that the sample-validation channel un-flagged the template.

This validates the FLAGGED-template Edge Case.

---

## 10. Cross-tenant isolation (SC-008)

Per the 2026-05-26 clarification, SC-008 is enforced by two
structural checks ONLY:

1. `HasProjectPermission` on the view (the `Project-Uuid` header
   is authorized against Connect's API), and
2. The serializer-layer FR-002b check that refuses any request
   whose `Project-Uuid` header does not equal the body's
   `project_uuid`.

WABA resolution itself flows through
`IntegrationsService.get_channel_app("wpp-cloud", dto.app_uuid)`,
which is a **global** lookup by `app_uuid` with no project
scoping. The frontend-supplied `app_uuid` is treated as trusted;
the use case does NOT cross-check it against
`template.integrated_agent.channel_uuid` and does NOT verify the
integrations response's `project_uuid`. The residual exposure
(compromised frontend / token-holding bypass caller) is accepted
as a known limitation pending a Connect-side `app_uuid →
project_uuid` scoping guarantee.

### Verify check (1) — `HasProjectPermission` refuses unauthorized projects

Fire the endpoint with a `Project-Uuid` header for a project the
operator is NOT authorized for:

```bash
curl -X POST \
  -H "Authorization: Bearer ${JWT_FOR_PROJECT_A}" \
  -H "Project-Uuid: <PROJECT_B_UUID>" \
  -H "Content-Type: application/json" \
  -d '{
    "template_body": "Hello",
    "app_uuid": "<any>",
    "project_uuid": "<PROJECT_B_UUID>"
  }' \
  "https://retail.example.com/api/v3/templates/<uuid>/sample/"
```

Expected HTTP 403 (DRF default from `HasProjectPermission`); no
audit log line is emitted by this endpoint (the rejection is
upstream of the view body).

### Verify check (2) — FR-002b refuses header ↔ body mismatch

Fire the endpoint with a `Project-Uuid` header for project A but
a body `project_uuid` for project B:

```bash
curl -X POST \
  -H "Authorization: Bearer ${JWT_FOR_PROJECT_A}" \
  -H "Project-Uuid: <PROJECT_A_UUID>" \
  -H "Content-Type: application/json" \
  -d '{
    "template_body": "Hello",
    "app_uuid": "<any>",
    "project_uuid": "<PROJECT_B_UUID>"
  }' \
  "https://retail.example.com/api/v3/templates/<uuid>/sample/"
```

Expected HTTP 400 response:

```jsonc
{
  "detail": "Project-Uuid header does not match body project_uuid",
  "error_code": "project_uuid_mismatch"
}
```

Audit log:

```text
[TemplateSampleValidation] project_uuid_mismatch: header_project_uuid=<A> body_project_uuid=<B> template_uuid=<uuid>
```

No Meta call and no integrations call are made (the serializer
refuses upstream of the use case).

### Residual `app_uuid` exposure (NOT enforced — documented known limitation)

If a token-holding caller bypasses the Retail-provided UI, holds
a valid Connect auth token for project A, and submits
`Project-Uuid = <A>`, `body.project_uuid = <A>`, and
`body.app_uuid = <project B's wpp-cloud app uuid>`, the Meta
sample call is routed against project B's WABA. The Meta sample
API is read-only on Meta's side (no template gets created or
modified at Meta from a sample call), and the local update gate
still keys off the `template_uuid` path param (which is
project-scoped via FR-002a's IntegratedAgent eligibility check),
so no Retail-side state of project B is mutated. This is
accepted per the 2026-05-26 clarification.

This validates SC-008.

---

## 11. Latency sanity check (SC-006)

For each step 3 / 5 / 8 above, measure the response time. The
target is p99 < 3 seconds. Most of the budget goes to the outbound
Meta call (typically 500ms–1.5s for a well-formed sample); Retail's
local hot path adds ~100–300ms for the DB reads + writes + optional
S3 upload.

```bash
time curl -X POST -H "..." -d '{ ... }' "https://retail.example.com/api/v3/templates/<uuid>/sample/"
```

Expected: `real 0m1.2s` ± variance. Hard ceiling: 3s at p99.

This validates SC-006.

---

## 12. Rollback

The feature ships zero schema changes and zero new env vars (per
plan.md Constraints section). To roll back:

1. Revert the deployment to the prior image.
2. The new endpoint URL (`/api/v3/templates/<uuid>/sample/`) is
   removed from the URL router; subsequent requests return HTTP
   404.
3. Any `Version` rows that were created with
   `status="APPROVED"` by this feature remain in place; they are
   indistinguishable from `Version` rows created by other paths
   (e.g. `AssignAgentUseCase`'s Direct Send template creation at
   `assign.py:421-438`). The dispatch path continues to read
   `Template.current_version.template_name` and renders the new
   content correctly.
4. No data migration is required on rollback.

To clean up rows created by this feature for forensic purposes
(very rarely needed):

```sql
-- Identify Versions created by this feature: rows with status='APPROVED'
-- that were NOT promoted by UpdateTemplateUseCase. The discriminator is
-- behavioral, not stored — the audit log is the source of truth.
-- Query the [TemplateSampleValidation] template_updated lines and join
-- on new_version_uuid.
```

No-op rollback is the expected operational mode — the feature is
additive and behaviorally consistent with the existing Direct Send
template management surface.
