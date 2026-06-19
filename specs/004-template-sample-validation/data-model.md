# Phase 1 Data Model: Template Sample Validation Endpoint for Direct Send

**Feature**: `004-template-sample-validation`
**Date**: 2026-05-26
**Spec**: `./spec.md`
**Research**: `./research.md`

This document captures the persisted-state and in-memory data
model required by the feature. The feature has **zero schema
changes** — no new model, no new column, no new index, no new
constraint, no new migration. PR-time verification:
`poetry run python manage.py makemigrations --check --dry-run`
MUST exit with code 0 (per FR-010).

At runtime, on a UTILITY-classified sample, the persisted-state
changes are exactly:

| Table | Statement | Field(s) | Mandatory? |
|---|---|---|---|
| `templates_version` | `INSERT` | new row (status defaults to `PENDING`) | yes |
| `templates_version` | `UPDATE` (single row) | `status = 'APPROVED'` via `update_fields=["status"]` | yes |
| `templates_template` | `UPDATE` (single row) | `metadata = <new>` via `update_fields=["metadata"]` | yes |
| `templates_template` | `UPDATE` (single row) | `current_version_id = <new>` via `update_fields=["current_version"]` | yes |
| `agents_integratedagent` | `UPDATE` (single row) | `config = <synced>` via `update_fields=["config"]` | optional — fires only when the abandoned-cart agent's header image config flips via `_sync_abandoned_cart_image_config` |

Total per UTILITY-classified request: **4 mandatory writes** (1
INSERT + 3 UPDATEs) + **1 optional UPDATE** (abandoned-cart sync)
+ **1 optional cache CLEAR** (paired with the abandoned-cart UPDATE
— Redis or `LocMemCache` in tests). The non-UTILITY path performs
**zero writes**; the FR-002a / FR-002b / FR-005a refusal paths
also perform zero writes.

The bulk of this document describes (a) the read interactions with
the four existing models the feature consults (`Project`,
`IntegratedAgent`, `Template`, `Version`) plus the outbound
integrations-engine call that resolves the WABA id, (b) the write
sites, and (c) the four in-memory DTOs (one inbound DTO, one
result DTO, two private helper enums). `ProjectOnboarding` is
**not** read by this endpoint — the WABA-id resolution flows
through `IntegrationsService.get_channel_app("wpp-cloud", app_uuid)`
per the 2026-05-26 clarification (see research Decision 3 and §3
below).

---

## 1. `Version.status` — `APPROVED` single-row write on UTILITY

**File**: `retail/templates/models.py` (read-only context — no
schema change ships against this model).

### Schema change

**None.** Both `PENDING` (the default when `_create_version` runs)
and `APPROVED` are already long-standing members of
`Version.STATUS_CHOICES` (`retail/templates/models.py:48-59`). The
`FLAGGED` value used by spec 003 also remains untouched. This
feature adds no value to the enum, adds no field to the model, and
adds no index / constraint to the table.

### Write sites

There are exactly two writes on `templates_version` per
UTILITY-classified request (1 INSERT + 1 UPDATE), both inside the
strategy helper `_create_version_with_options` (refactored from
`UpdateNormalTemplateStrategy._create_version` per research
Decision 4):

```python
# (a) INSERT — same path the legacy PATCH endpoint uses today.
#     Always fires when the use case reaches the UTILITY branch.
version = Version(
    template_name=f"weni_{template.name}_{timestamp_str}",
    template=template,
    integrations_app_uuid=payload["app_uuid"],
    project=project,
)
version.full_clean()
version.save()
# version.status defaults to "PENDING" per Version.status's
# default value (retail/templates/models.py:69).

# (b) UPDATE — fires only when status="APPROVED" (the new endpoint's call).
#     Skipped by the legacy PATCH endpoint (which passes status="PENDING"
#     and matches the default — no second UPDATE needed).
if status != "PENDING":
    version.status = status            # "APPROVED" for this feature
    version.save(update_fields=["status"])
```

- **Write pre-condition**: Meta returned `category == "UTILITY"`
  (FR-005b) AND the FR-002a Direct-Send-eligibility check passed
  (`template.integrated_agent.config["direct_send"] is True`).
- **Write post-conditions**:
  - After (a): a new row exists on `templates_version` with a
    fresh `uuid`, `template_name=weni_<name>_<timestamp>`,
    `integrations_app_uuid=<dto.app_uuid>`,
    `project_id=<resolved_project.id>`, and `status="PENDING"`.
  - After (b): the same row's `status` column is `"APPROVED"`.
- **Transaction boundary**: implicit per-statement transaction
  (Django default — research Decision 8). No `@transaction.atomic`
  wrap. The two writes are sequenced, not atomic; partial-failure
  modes are operationally safe (a `PENDING` row with no
  `APPROVED` follow-up is a stale row the next submission
  replaces; never corrupts dispatch).
- **Row identification**: write (a) creates a fresh row via
  `Version(...).save()`; write (b) targets the same `Version`
  instance via the Python reference, which Django translates to
  `UPDATE ... WHERE id = <pk>`. No cross-row write is involved.
- **Update scope**: `update_fields=["status"]` is mandatory on (b)
  — the intent is "flip status to APPROVED, nothing else". Omitting
  `update_fields` would force Django to re-write every column,
  risking accidental staleness if the in-memory snapshot diverged.

### Read sites

The use case reads `template.current_version` (via the OneToOne
FK from `templates_template.current_version_id`) twice:

```python
# (1) Audit-log "previous_current_version_uuid" + status — captured
#     pre-write to feed FR-008a's template_updated event.
previous_current_version_uuid = (
    template.current_version.uuid if template.current_version else None
)
previous_current_version_status = (
    template.current_version.status if template.current_version else None
)

# (2) Post-write — no explicit read; the strategy helper has the
#     new Version object in scope and writes Template.current_version
#     directly via the FK setter.
template.current_version = new_version
template.save(update_fields=["current_version"])
```

The pre-write read happens AFTER the Template is loaded with
`select_related("integrated_agent")` (no `select_related("current_version")`
is added — `current_version` is a OneToOne FK whose forward access
fires a single follow-up query when first touched; this is
acceptable because it happens at most once per request on the hot
path, and only on the UTILITY branch).

### Audit-log fields

Per FR-008a / spec.md A11, the `template_updated` audit-log line
carries the new and previous Version identifiers + statuses:

```text
[TemplateSampleValidation] template_updated:
  template_uuid=<uuid>
  new_version_uuid=<new_version.uuid>
  new_version_status=APPROVED
  previous_current_version_uuid=<prior_version_uuid_or_null>
  previous_current_version_status=<prior_status_or_null>
```

Both `new_version_uuid` and `previous_current_version_uuid` are the
public `Version.uuid` identifier (per the project's "integer PK +
separate UUID for external identification" convention — see
constitution Principle V); they are NOT the integer `Version.id`.
The audit-log dashboards filter on UUIDs because the integer PKs are
internal storage identifiers.

---

## 2. `Template.metadata` and `Template.current_version` — two single-column writes

**File**: `retail/templates/models.py` (read-only context — no
schema change ships against this model).

### Schema change

**None.** Both `metadata` (JSONField) and `current_version` (OneToOne
FK) are pre-existing columns on `templates_template`.

### Write sites

Two writes per UTILITY-classified request, both inside the strategy
helper functions per research Decision 4:

```python
# (a) Inside _apply_metadata_update (refactored from
#     UpdateNormalTemplateStrategy.update_template lines 228-229).
template.metadata = updated_metadata   # dict produced by
                                       # TemplateMetadataHandler.build_metadata
                                       # + post_process_translation
template.save(update_fields=["metadata"])

# (b) Inside _create_version_with_options when
#     advance_current_version=True. Skipped by the legacy PATCH
#     endpoint (which passes advance_current_version=False).
if advance_current_version:
    template.current_version = new_version
    template.save(update_fields=["current_version"])
```

- **Write pre-condition**: same as Version writes — UTILITY
  classification AND FR-002a gate passed.
- **Write post-conditions**:
  - After (a): `templates_template.metadata` JSON column is the
    canonical local-shape dict (`body`, `body_params`, `header`,
    `footer`, `buttons`, `category`, `language` keys) with raw
    `{{N}}` placeholders preserved (A7) and IMAGE-header `text`
    holding the S3 URL (not the base64 input — the S3 upload
    happened upstream of the Meta call per A9).
  - After (b): `templates_template.current_version_id` points to
    the new Version row's PK.
- **Update scope**: `update_fields=["metadata"]` on (a) and
  `update_fields=["current_version"]` on (b) — same precedent as
  the legacy strategy's `template.save(update_fields=["metadata"])`
  at `retail/templates/strategies/update_template_strategies.py:229`.
- **Side effect** (inherited from `_apply_metadata_update`'s
  `_sync_abandoned_cart_image_config` call):
  `agents_integratedagent.config["abandoned_cart"]["header_image_type"]`
  may be flipped from `"first_item"` to `"no_image"` (or vice
  versa) when the abandoned-cart agent's template gets a header
  image added / removed. This is a single-row UPDATE on
  `agents_integratedagent.config` (JSONField), only fires for
  templates whose IntegratedAgent.agent.uuid matches
  `settings.ABANDONED_CART_AGENT_UUID`. The cache clear that
  follows it is described in §6 below.

### Read sites

The use case reads `Template` once via `select_related("integrated_agent")`:

```python
template = (
    Template.objects
    .select_related("integrated_agent")
    .get(uuid=template_uuid)
)
```

After this single read, all subsequent operations on
`template.integrated_agent` are free (no follow-up query). The
`template.metadata.get("category")` access is JSON-column read on
the in-memory snapshot; no extra DB call.

### `current_version.template_name` — dispatch-side read (downstream, unchanged)

Spec 002's `Broadcast.build_direct_send_message` reads
`template.current_version.template_name` on every dispatch
(`retail/agents/domains/agent_webhook/services/broadcast.py:83`).
After write (b) above, the next dispatch reads the new Version's
`template_name` (a fresh `weni_<name>_<timestamp>` string) and uses
it as Meta's `direct_send_config.template_name` — binding the
broadcast to a new Meta-auto-created template with the updated
content. This is the SC-004 latency property: the next dispatch
sees the new template_name with no cache lag and no asynchronous
convergence window.

---

## 3. WABA-id resolution via `IntegrationsService.get_channel_app` — outbound HTTP call

**File**: `retail/services/integrations/service.py:372-389`
(read-only context — no schema change ships against this service).

### Schema change

**None.** The feature consumes the existing
`IntegrationsService.get_channel_app(apptype, app_uuid)` method
that already returns `Optional[Dict]` (the service swallows
`CustomAPIException` to `None`); no service-layer signature change
is introduced. **`ProjectOnboarding` is NOT read by this endpoint
for WABA resolution** (per research Decision 3 — the local
snapshot can drift from the live integrations state when a WABA
is reconfigured outside the onboarding flow).

### Read site

One outbound HTTP call per request (the very first network call
after the FR-002a gating succeeds, and before the Meta call):

```python
app = self.integrations_service.get_channel_app(
    "wpp-cloud", dto.app_uuid
)
waba_id = ((app or {}).get("config") or {}).get("waba", {}).get("id")
if not waba_id:
    self._emit_waba_not_configured(
        project_uuid=dto.project_uuid,
        app_uuid=dto.app_uuid,
        integrations_response_present=bool(app),
    )
    raise WabaNotConfiguredError(
        f"WABA not configured for project {dto.project_uuid}"
    )
```

The `if not waba_id` guard handles three failure modes uniformly
per FR-005a, all of which collapse to one user-facing response per
the 2026-05-26 clarification:

| # | Failure mode                                                         | `app` value | `bool(app)` (audit flag) |
| - | -------------------------------------------------------------------- | ----------- | ------------------------ |
| a | Integrations infra failure (5xx / network / timeout — swallowed)     | `None`      | `False`                  |
| b | Integrations returns no app for the supplied `app_uuid` (swallowed)  | `None`      | `False`                  |
| c | Integrations returns a dict but `config["waba"]["id"]` is missing/empty | dict     | `True`                   |

All three surface as HTTP 400 with `error_code = "waba_not_configured"`.
The audit-log discriminator (`integrations_response_present`)
distinguishes "service down / bad `app_uuid`" (`False`) from "app
exists but unconfigured" (`True`) per FR-008a — see §7 for the
full event payload.

### Field-path source of truth

The `app["config"]["waba"]["id"]` JSON path is the same one
`ConfigureOneClickPaymentUseCase._fetch_channel_info` consumes at
`retail/projects/usecases/configure_one_click_payment.py:192`. The
new use case reuses an existing service-layer contract rather
than introducing a parallel resolution path. The
`IntegrationsService.get_channel_app` swallow-to-None on
`CustomAPIException` is preserved unchanged — other call sites
stay untouched.

### Write site

**None.** The use case never writes to the integrations engine,
never writes to `ProjectOnboarding`, never writes to any
WABA-related local state.

---

## 4. `IntegratedAgent.config["direct_send"]` — read-only eligibility gate

**File**: `retail/agents/domains/agent_integration/models.py`
(read-only context — no schema change ships against this model).

### Schema change

**None.** The `config` JSONField is pre-existing on
`agents_integratedagent`. The `direct_send` boolean is set at
assignment time by `AssignAgentUseCase`
(`retail/agents/domains/agent_integration/usecases/assign.py:160-162`):

```python
if direct_send:
    initial_config["direct_send"] = True
```

### Read site

One read per request (immediately after the Template load,
co-resident with `template.integrated_agent` via
`select_related`):

```python
is_eligible = bool(
    template.integrated_agent
    and template.integrated_agent.config.get("direct_send", False)
)
if not is_eligible:
    raise NotDirectSendEligibleError(...)
```

Two failure modes:

- `template.integrated_agent is None` — custom template with no
  IntegratedAgent FK.
- `template.integrated_agent.config.get("direct_send", False) is
  False` — IntegratedAgent exists but is not Direct Send-enabled.

Both surface as HTTP 400 with `error_code = "not_direct_send_eligible"`
(FR-007e). The audit-log `not_direct_send_eligible` event records
the resolved flag value (`null` for the first case, `False` for
the second) so dashboards can distinguish them.

### Write site

**None.** The use case never mutates `IntegratedAgent`. The
side-effect `agents_integratedagent.config["abandoned_cart"]["header_image_type"]`
write from `_sync_abandoned_cart_image_config` (§2 above) is on
a DIFFERENT key (`abandoned_cart`, not `direct_send`) and is
inherited from the legacy strategy; the gating predicate
`direct_send` is read-only.

---

## 5. `Project` — read-only tenant boundary

**File**: `retail/projects/models.py` (read-only context — no
schema change ships against this model).

### Schema change

**None.**

### Read sites

The use case touches `Project` only transitively, via one
relationship:

- `template.integrated_agent.project` — read by
  `_apply_metadata_update`'s downstream call to
  `_sync_abandoned_cart_image_config` (which checks
  `integrated_agent.agent.uuid` against the abandoned-cart
  agent's UUID — no `Project` read in that path; mentioned for
  completeness).

The use case never reads `Project` directly (no
`Project.objects.get(uuid=...)` call) and never reads
`ProjectOnboarding` (the WABA-id resolution flows through the
integrations engine per §3). The `HasProjectPermission`
permission class on the ViewSet reads `Project` indirectly via
its Connect-service call, but that's upstream of the use case.

### Write site

**None.**

---

## 6. Cache (Redis) — read-only on the abandoned-cart cache clear

**File**: `retail/agents/shared/cache.py` (read-only context — no
schema change).

The legacy strategy's `_sync_abandoned_cart_image_config` triggers
a `IntegratedAgentCacheHandlerRedis.clear_cached_agent(integrated_agent.uuid)`
call when the abandoned-cart `header_image_type` flips
(`retail/templates/strategies/update_template_strategies.py:200-210`).
This side effect is inherited by the new endpoint's
`_apply_metadata_update` composition. The cache key
(`integrated_agent.uuid`) is identified, the cache is cleared
synchronously, and the next webhook dispatch repopulates it. No
new cache key is introduced.

For tests, `LocMemCache` is used via the existing `BaseTestMixin`
setup; no Redis connection is established in the test suite
(Constitution Principle III).

---

## 7. In-memory DTOs and Result objects

Four in-memory dataclasses live inside
`retail/templates/usecases/validate_template_sample.py`:

### `ValidateTemplateSampleDTO` (input)

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ValidateTemplateSampleDTO:
    """Validated, immutable payload passed from the view to the use case.

    Built by the view from ValidateTemplateSampleSerializer.validated_data;
    consumed by ValidateTemplateSampleUseCase.execute(...).
    """

    template_uuid: str
    template_body: Optional[str]
    template_header: Optional[str]
    template_footer: Optional[str]
    template_button: Optional[List[Dict[str, Any]]]
    template_body_params: Optional[List[Any]]
    app_uuid: str
    project_uuid: str
    parameters: Optional[List[Dict[str, Any]]]
    language: Optional[str]
```

### `ValidateTemplateSampleResult` (output)

```python
@dataclass(frozen=True)
class ValidateTemplateSampleResult:
    """Use-case return value shaped for the HTTP 200 response body.

    The view shapes the HTTP body as Response(result.to_dict(), 200).
    """

    category: str
    template_updated: bool
    template: "Template"               # ORM instance; serialized by view
    meta_sample_response: Dict[str, Any]  # raw Meta body

    def to_dict(self) -> Dict[str, Any]:
        from retail.templates.serializers import ReadTemplateSerializer
        return {
            "category": self.category,
            "template_updated": self.template_updated,
            "template": ReadTemplateSerializer(self.template).data,
            "meta_sample_response": self.meta_sample_response,
        }
```

The use case constructs the result with the in-memory ORM
`Template` instance; the view's serializer wrapper at
`to_dict()` time produces the JSON shape. This keeps the use case
framework-agnostic (no `ReadTemplateSerializer` import would be
needed except inside `to_dict()` which is a thin formatting layer;
the use case logic is decoupled).

### `EventName` enumeration (private helper)

```python
from enum import Enum


class EventName(str, Enum):
    """Closed enumeration for the FR-008a event_name discriminator."""

    RECEIVED = "received"
    META_SAMPLE_SUBMITTED = "meta_sample_submitted"
    META_SAMPLE_RESPONSE = "meta_sample_response"
    TEMPLATE_UPDATED = "template_updated"
    UPDATE_SKIPPED = "update_skipped"
    META_ERROR = "meta_error"
    META_INVALID_RESPONSE = "meta_invalid_response"
    WABA_NOT_CONFIGURED = "waba_not_configured"
    NOT_DIRECT_SEND_ELIGIBLE = "not_direct_send_eligible"
    PROJECT_UUID_MISMATCH = "project_uuid_mismatch"
    LOCAL_UPDATE_FAILED_AFTER_META_APPROVAL = (
        "local_update_failed_after_meta_approval"
    )
```

#### `waba_not_configured` event payload

Per FR-008a (updated by the 2026-05-26 clarification), the
`waba_not_configured` line carries the discriminator field that
lets dashboards separate the integrations-side failure modes
without leaking the distinction into the operator-facing response:

```text
[TemplateSampleValidation] waba_not_configured:
  project_uuid=<uuid>
  app_uuid=<uuid>
  integrations_response_present=<true|false>
```

| Field                          | Type       | Meaning                                                                                                                                                       |
| ------------------------------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `project_uuid`                 | UUID       | The authenticated project (taken from the verified body `project_uuid`, which equals the `Project-Uuid` header by FR-002b).                                   |
| `app_uuid`                     | UUID       | The frontend-supplied `app_uuid` passed to `IntegrationsService.get_channel_app("wpp-cloud", app_uuid)`.                                                       |
| `integrations_response_present` | bool      | `false` when the integrations call returned `None` (infra failure OR no app for the supplied `app_uuid`); `true` when it returned a dict but the dict's config had no usable `waba_id`. |

Log level: **WARNING** per FR-008b. PII redaction: not applicable
— all three fields are tenant identifiers per FR-008c's carve-out
for UUIDs.

The single user-facing HTTP 400 response
(`error_code = "waba_not_configured"`) does NOT echo
`integrations_response_present`; root-cause analysis lives in the
audit log only per the FR-005a single-class collapse.

### `MetaSampleType` enumeration (private helper)

```python
class MetaSampleType(str, Enum):
    """The Meta message_samples interactive sub-type for audit logging."""

    TEXT = "text"
    INTERACTIVE_CTA_URL = "interactive.cta_url"
    INTERACTIVE_BUTTON = "interactive.button"
```

This is logged on the `meta_sample_submitted` event so dashboards
can compute "what fraction of samples are CTA URL vs reply
buttons" per template type.

---

## 8. Domain exceptions (raised by use case, caught by view)

Four new domain exceptions added to `retail/templates/exceptions.py`:

```python
class NotDirectSendEligibleError(Exception):
    """Raised when the template's IntegratedAgent does not have
    direct_send enabled per FR-002a. View translates to HTTP 400
    with error_code='not_direct_send_eligible'."""


class WabaNotConfiguredError(Exception):
    """Raised when IntegrationsService.get_channel_app("wpp-cloud",
    app_uuid) returns None (infra failure or no app for app_uuid)
    OR returns a dict whose config["waba"]["id"] is missing/empty
    per FR-005a. View translates to HTTP 400 with
    error_code='waba_not_configured' (a single user-facing class —
    the audit log's integrations_response_present flag discriminates
    the underlying mode per §7)."""


class MetaSampleUnavailableError(Exception):
    """Raised when the outbound Meta call failed (CustomAPIException
    or unexpected exception) per FR-005c. Carries the original
    HTTP status code, Meta error code, and Meta error message.
    View translates to HTTP 502 with error_code='meta_unavailable'."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        meta_response: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.meta_response = meta_response


class MetaInvalidResponseError(Exception):
    """Raised when Meta returned HTTP 200 but the body lacks a
    category field or carries success=false per FR-005b. View
    translates to HTTP 502 with error_code='meta_invalid_response'."""

    def __init__(
        self,
        message: str,
        *,
        meta_response: Dict[str, Any],
    ):
        super().__init__(message)
        self.meta_response = meta_response
```

The view's exception-translation block:

```python
try:
    result = use_case.execute(dto)
except NotDirectSendEligibleError:
    return Response(
        {"detail": "Template is not Direct Send-eligible",
         "error_code": "not_direct_send_eligible"},
        status=400,
    )
except WabaNotConfiguredError:
    return Response(
        {"detail": "WABA not configured for this project",
         "error_code": "waba_not_configured"},
        status=400,
    )
except MetaSampleUnavailableError as exc:
    body = {"detail": "Meta sample submission failed",
            "error_code": "meta_unavailable"}
    # `is not None` (not truthiness) so a parseable-but-empty
    # Meta error envelope ({}) is still surfaced to the frontend.
    if exc.meta_response is not None:
        body["meta_response"] = exc.meta_response
    return Response(body, status=502)
except MetaInvalidResponseError as exc:
    return Response(
        {"detail": "Meta did not return a category",
         "error_code": "meta_invalid_response",
         "meta_response": exc.meta_response},
        status=502,
    )
```

The view also relies on DRF's default `NotFound` translation for
the missing-Template-UUID case (parity with the legacy PATCH
endpoint per FR-011).

---

## 9. Sequencing summary (UTILITY happy path)

For the happy path (UTILITY classification on a Direct
Send-eligible template), the view + use case execute the
following sequence:

```text
0. View: ValidateTemplateSampleSerializer.is_valid(raise_exception=True)
   → FR-002b check: header Project-Uuid must equal body project_uuid;
     otherwise serializer raises ValidationError → HTTP 400 /
     error_code=project_uuid_mismatch (no use case invocation)
1. _emit RECEIVED log line
2. Template.objects.select_related("integrated_agent").get(uuid=...)
   → 1 DB read
3. FR-002a gate check on integrated_agent.config["direct_send"]
   → no DB read (in-memory check)
4. IntegrationsService.get_channel_app("wpp-cloud", dto.app_uuid)
   → 1 outbound Connect-side HTTP call
5. WABA-id resolution: read app["config"]["waba"]["id"] (in-memory
   dict traversal); raise WabaNotConfiguredError if None / empty
   (FR-005a — collapses 3 failure modes; audit log carries the
   discriminating integrations_response_present flag per §7)
6. _emit META_SAMPLE_SUBMITTED log line
7. _build_meta_sample_body (translator, pure function)
   → If IMAGE header is base64, S3 upload happens here (1 S3 round-trip)
8. MetaService.submit_template_sample (outbound HTTP call)
   → 1 Meta round-trip (the dominant latency)
9. _emit META_SAMPLE_RESPONSE log line
10. _apply_metadata_update on the strategy
    → 1 DB write (UPDATE templates_template SET metadata = ...)
    → Optional: 1 DB write (UPDATE agents_integratedagent SET config = ...)
                + 1 cache CLEAR (synchronous)
11. _create_version_with_options(status="APPROVED",
                                  advance_current_version=True)
    → 1 DB write (INSERT INTO templates_version)
    → 1 DB write (UPDATE templates_version SET status = 'APPROVED')
    → 1 DB write (UPDATE templates_template SET current_version_id)
12. _emit TEMPLATE_UPDATED log line
13. Return ValidateTemplateSampleResult
```

Total operations on the UTILITY happy path: **1 DB read**
(Template — `ProjectOnboarding` is NOT read by this endpoint per
§3) + **4 mandatory DB writes** (Template.metadata, Version
INSERT, Version.status, Template.current_version_id) + **1
optional DB write** (IntegratedAgent.config — only for the
abandoned-cart agent's header-image flip) + **1 optional cache
clear** (paired with the optional write) + **1 optional S3 upload**
(only for new base64 IMAGE headers) + **2 outbound HTTP calls**
(integrations engine + Meta, serial — worst case
`t_integrations + t_meta`). The latency budget of SC-006 (p99 < 3s)
accommodates these with the Meta call dominating.

For the non-UTILITY path the sequence stops at step 9 (no local
writes); for the FR-002b-refused path the sequence stops at step 0
(no use case invocation, no DB read, no integrations call, no
Meta call); for the FR-002a-refused path the sequence stops at
step 3 (no integrations call, no Meta call, no writes); for the
FR-005a-refused path the sequence stops at step 5 (no Meta call,
no writes — the integrations call already fired and is what
triggered the refusal).

---

## 10. `Project-Uuid` header ↔ body `project_uuid` equality (FR-002b)

**File**: `retail/templates/serializers.py` — the new
`ValidateTemplateSampleSerializer.validate_project_uuid` method.

### Schema change

**None.** The check is purely behavioral on existing request
fields.

### Read sites

The serializer reads two sources:

```python
def validate_project_uuid(self, value: str) -> str:
    """FR-002b — refuse when the Project-Uuid header does not match
    the body's project_uuid. The header is the trust source for
    HasProjectPermission (retail/internal/permissions.py:67), so
    the body's project_uuid MUST agree with it to keep the WABA
    resolution scoped to the authorized tenant (SC-008)."""
    request = self.context.get("request")
    header_project_uuid = (
        request.headers.get("Project-Uuid") if request else None
    )
    if header_project_uuid and header_project_uuid != value:
        raise serializers.ValidationError(
            "Project-Uuid header does not match body project_uuid",
            code="project_uuid_mismatch",
        )
    return value
```

The view passes the request via the DRF default
`Serializer(context={"request": request})` pattern (which the
`@action` decorator handles automatically on a ViewSet's
`get_serializer_context` — but the new action constructs the
serializer manually, so the view MUST pass
`context={"request": request}` explicitly).

### Write sites

**None.** The check is read-only and rejection-only.

### Audit log

The view's serializer-error translation block emits a single
`[TemplateSampleValidation] project_uuid_mismatch:
header_project_uuid=<a> body_project_uuid=<b> template_uuid=<uuid>`
WARNING-level line per FR-008a / FR-008b before returning the
HTTP 400 response. The header / body project UUIDs are tenant
identifiers (not customer-facing content), so they are logged
verbatim per the FR-008c carve-out for UUIDs.

### Failure mode interaction with cross-tenant isolation (SC-008)

Per the 2026-05-26 clarification (Q2 — trust-the-frontend
`app_uuid`), SC-008 collapses to **two** structural defenses; the
former third defense via `ProjectOnboarding.filter(project__uuid=...)`
is gone because the WABA lookup is now a global call by `app_uuid`
with no project scoping:

1. `HasProjectPermission` (view layer) validates the `Project-Uuid`
   header against Connect's authorization API. An operator who is
   not authorized for the header's project never reaches the
   serializer.
2. `ValidateTemplateSampleSerializer.validate_project_uuid`
   (serializer layer, FR-002b) refuses any request whose body
   `project_uuid` does not equal the verified-trusted header. This
   pins the body's `project_uuid` field to the authorized tenant
   and closes the body-spoof vector for every project-scoped value
   the downstream stack relies on (audit log, error envelope,
   abandoned-cart sync side effect, etc.).

The WABA lookup itself (FR-005a) flows through
`IntegrationsService.get_channel_app("wpp-cloud", dto.app_uuid)`
— a global lookup by `app_uuid` with no project scoping. The
frontend-supplied `app_uuid` is treated as trusted-and-authenticated;
no use-case-level cross-check against
`template.integrated_agent.channel_uuid` and no post-call check
against the integrations response's `project_uuid` are performed.
A compromised frontend (or a token-holding caller bypassing the
Retail-provided UI) holding a valid Connect auth token for project
A can therefore submit `app_uuid = <project B's wpp-cloud app uuid>`
and route a Meta sample to project B's WABA. This residual
exposure is explicitly accepted in SC-008 as a known limitation
pending a Connect-side `app_uuid → project_uuid` scoping
guarantee, and is bounded operationally by two facts: (i) the Meta
sample API is read-only on Meta's side (no template gets created
or modified at Meta from a sample call), and (ii) the local update
gate downstream still keys off the `template_uuid` path param,
which is project-scoped via FR-002a's IntegratedAgent eligibility
check — so no Retail-side state of project B is mutated by such a
cross-tenant call.

Together, defenses (1) and (2) make project-uuid-body spoofing
impossible for any authenticated caller; the residual `app_uuid`
exposure is the documented known limitation.
