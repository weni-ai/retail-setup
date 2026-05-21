# Contract — Integrations Channel-App GET (consumed by Retail)

**Feature**: `002-direct-send-broadcasts`
**Consumer**: `retail-setup` — `IntegrationsClient.get_channel_app`
(existing), called from `IntegrationsService.get_channel_app`.
**Producer**: Integrations Engine —
`GET {INTEGRATIONS_REST_ENDPOINT}/api/v1/apptypes/{apptype}/apps/{app_uuid}/`.
**Auth**: `Authorization: Bearer {InternalAuthentication.headers}`
(existing internal token).

This contract is **already in production for the webchat configuration
flow**; this document only specifies the new field that Retail reads
to gate the Direct Send path at agent-assignment time (FR-002).

---

## 1. Request

```http
GET /api/v1/apptypes/wpp-cloud/apps/{app_uuid}/ HTTP/1.1
Authorization: Bearer {INTERNAL_TOKEN}
Content-Type: application/json
```

| Field      | Type   | Notes                                                                                  |
| ---------- | ------ | -------------------------------------------------------------------------------------- |
| `apptype`  | string | Always `"wpp-cloud"` for the OrderStatus assignment flow (the only apptype where Direct Send is meaningful in v1). |
| `app_uuid` | string | The WhatsApp Cloud app UUID supplied by the operator (`request.query_params["app_uuid"]`). |

---

## 2. Successful response (Retail-relevant subset)

HTTP 200 with body:

```jsonc
{
  "uuid":         "<app_uuid>",
  "code":         "wpp-cloud",
  "project_uuid": "<project_uuid>",
  "config": {
    "wa_business_id":   "<WABA_ID>",
    "wa_phone_number_id": "<PHONE_NUMBER_ID>",
    "direct_send":       true,                      // NEW field consumed by Retail (boolean)
    /* any other fields Integrations sets — Retail ignores them */
  },
  "created_on": "2026-04-01T00:00:00Z"
}
```

Retail consumes **only** `config.direct_send`. The boolean is the
authoritative source of truth for whether the WhatsApp channel
has Direct Send enabled (Beta access granted by Meta and recorded
by Integrations).

### 2.1 Field definition

| Path                  | Type    | Required | Default when absent | Notes                                                                                  |
| --------------------- | ------- | -------- | ------------------- | -------------------------------------------------------------------------------------- |
| `config.direct_send`  | boolean | no       | `false`             | When `true`, the channel is on Meta's Direct Send Beta. When absent or `false`, Retail uses the legacy template-creation pipeline. |

The "absent → `false`" rule is the conservative default mandated by
FR-005 and Story 2 scenario 3 — Retail never opt-ins a project to
Direct Send because of an ambiguous channel response.

---

## 3. Failure modes

| Mode                                          | HTTP / `service` return        | Retail-side handling                                                                            |
| --------------------------------------------- | ------------------------------ | ----------------------------------------------------------------------------------------------- |
| App not found                                 | 404 → service returns `None`   | Default to `direct_send=False`. Warning log: `[DirectSend] channel_lookup_failed`.              |
| Auth failure                                  | 401/403 → service returns `None` | Same as above.                                                                                  |
| Integrations server error                     | 5xx → service returns `None`   | Same as above.                                                                                  |
| Network error                                 | Exception → service returns `None` | Same as above.                                                                                  |
| 200 OK with no `config` key OR no `direct_send` key in `config` | service returns dict | Default to `direct_send=False`. No warning (this is the steady-state for Direct-Send-disabled channels). |

The service contract is unchanged from today — `get_channel_app`
already swallows `CustomAPIException` and returns `None`. The new
caller is just an additional consumer.

---

## 4. Retail-side eligibility check

The assignment use case combines two signals to decide whether to
take the Direct Send path:

1. The agent must be the OrderStatus agent: `agent.uuid == settings.ORDER_STATUS_AGENT_UUID` (FR-019).
2. The channel must report Direct Send enabled (this contract).

Both signals must be `True` to take the Direct Send path; otherwise
the legacy template-creation pipeline runs unchanged (FR-005, FR-019,
Story 4).

```python
def _resolve_direct_send_flag(self, agent: Agent, app_uuid: UUID) -> bool:
    if str(agent.uuid) != getattr(settings, "ORDER_STATUS_AGENT_UUID", ""):
        return False
    app = self.integrations_service.get_channel_app("wpp-cloud", str(app_uuid))
    if app is None:
        logger.warning(
            f"[DirectSend] channel_lookup_failed: agent={agent.uuid} "
            f"app_uuid={app_uuid} — defaulting to direct_send=False"
        )
        return False
    return bool((app.get("config") or {}).get("direct_send", False))
```

---

## 5. Idempotency and caching

GET — naturally idempotent. The contract is read once per assignment
attempt and the result is persisted as
`IntegratedAgent.config["direct_send"]` (an optional key inside the
existing `config` JSONField; absence is interpreted as `False` —
data-model.md §1 Decision). No Retail-side cache is added;
subsequent broadcasts read the persisted flag from `config`, never
the channel.

### 5.1 Snapshot lifetime (consistency with spec assignment-time snapshot)

The "read-once-at-assignment" property of this contract is the
implementation of the spec's "snapshot at assignment time" guarantee
(spec FR-002 Assumption, research Decision 1):

- A successful `AssignAgentUseCase.execute` reads the channel-app
  flag exactly once and writes
  `IntegratedAgent.config["direct_send"]` (via
  `agent.save(update_fields=["config"])`) inside the same atomic
  transaction. No subsequent broadcast or background task re-reads
  the channel-app endpoint to refresh the flag.
- An operator-initiated re-assignment (e.g. after an FR-003d
  failure, or after the operator wants to flip the path on a
  channel whose Direct Send status changed) is a NEW assignment
  attempt — a new at-most-once read of the channel-app endpoint,
  a new snapshot.
- The channel-app endpoint MAY be flipped between assignment
  attempts; Retail does not detect or compensate for the flip
  outside an explicit re-assignment (spec Edge Cases —
  "Channel Direct Send flag changes after agent assignment").

### 5.2 Failure semantics under retry

If a transient Integrations 5xx surfaces during an assignment, the
use case defaults to `direct_send=False` and logs
`[DirectSend] channel_lookup_failed` (§3, §4). The IntegratedAgent
is created with the conservative default. The operator MAY retry
the assignment; the retry is a new attempt with a fresh channel-app
read. Retail does NOT auto-retry the channel-app GET inside a
single assignment attempt (retry budget = 0 — see
`research.md` Decision 15 and `plan.md` Constraints — Idempotency
& retry safety).

---

## 6. Out-of-band changes to the channel's Direct Send flag

The spec is explicit (Edge Cases — "Channel Direct Send flag changes
after agent assignment"): if Integrations later flips the channel
from enabled to disabled (or vice-versa), the IntegratedAgent's
`direct_send` flag does NOT auto-resync. The snapshot at assignment
time is the source of truth until the agent is re-assigned.

A future feature may introduce a re-sync mechanism; this is out of
scope for v1 and explicitly NOT a requirement of this contract.

---

## 7. Settings touched

| Setting                       | Used by                                                              | Already configured? |
| ----------------------------- | -------------------------------------------------------------------- | ------------------- |
| `INTEGRATIONS_REST_ENDPOINT`  | base URL of the Integrations Engine                                   | yes                 |
| `ORDER_STATUS_AGENT_UUID`     | Retail-side eligibility check (Section 4)                             | yes                 |

No new environment variable is required for this feature.

---

## 8. Tenant-isolation requirements (spec FR-043)

The contract is the per-tenant boundary at the assignment surface
— it is the single source of truth for the channel-to-project
binding. Spec FR-043 requires that the `app_uuid` query parameter
and the `Project-Uuid` header form a TENANT-BINDING PAIR validated
at assignment time.

### 8.1 Required cross-validation

The `project_uuid` field on the response body (Section 2) MUST
equal the `Project-Uuid` header on the assignment request. On
mismatch, the assignment MUST be DENIED with HTTP 403 and an audit
log entry that includes both project UUIDs and the operator
identifier. The denial MUST be observable as
`[DirectSend] channel_project_mismatch: project_uuid_request={...}
project_uuid_app={...} operator={...} app_uuid={...}` (ERROR level).

This validation closes the cross-tenant attack surface described
in spec.md Edge Cases ("Operator with permission on project A
passes project B's `app_uuid` (or `channel_uuid`) in the assignment
request").

### 8.2 v1 implementation status

For v1, the cross-validation is satisfied TRANSITIVELY through
three layers — DRF's `HasProjectPermission` on `AssignAgentView`
(operator must be a contributor / moderator of `Project-Uuid`),
Integrations Engine's own authorization on
`GET /api/v1/apptypes/wpp-cloud/apps/{app_uuid}/` (a cross-project
read returns 404 because the requestor is not authorized for the
`app_uuid`'s owner project), and `IntegrationsService.get_channel_app(...)`'s
fail-closed `None` return on any HTTP error.

The explicit Retail-side cross-validation (`app["config"]["project_uuid"]
== request.headers["Project-Uuid"]`) is captured as a defense-in-depth
follow-up and is NOT part of this PR. The follow-up scope is
documented in `plan.md` Constraints — Tenant isolation.

### 8.3 Persisted snapshot

The validated channel-to-project binding is persisted on
`IntegratedAgent.channel_uuid`. Two `IntegratedAgent` rows in
different projects MUST NEVER share the same `channel_uuid`,
modulo the upstream guarantee that Integrations Engine never
issues the same channel UUID for two channels (Section 9 below).

---

## 9. Upstream dependency on Integrations Engine

Retail TRUSTS Integrations Engine to enforce two tenant-isolation
preconditions (spec.md Assumptions; spec FR-043):

1. **Channel-app authorization**: a request for an `app_uuid` that
   does NOT belong to the requestor's project returns 404 (or
   403). This is the precondition that makes Section 8.2's
   transitive validation safe at v1.
2. **Channel UUID global uniqueness**: Integrations Engine never
   issues the same `channel_uuid` for two distinct channels (across
   any tenant). This is the precondition that lets Retail use
   `IntegratedAgent.channel_uuid` as a per-channel scalar without a
   tenant join — every `channel_uuid` value resolves to exactly one
   channel and therefore exactly one project.

A regression in either precondition would break Retail's
tenant-isolation guarantee at the assignment surface and is a
known dependency. Spec.md Assumptions documents the trust
boundary; Retail does not currently audit Integrations Engine for
either precondition.
