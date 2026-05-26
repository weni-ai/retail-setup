# Implementation Plan: Template Sample Validation Endpoint for Direct Send

**Branch**: `004-template-sample-validation`
**Date**: 2026-05-26
**Spec**: [./spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-template-sample-validation/spec.md`

## Summary

Expose a new operator-facing HTTP endpoint
(`POST /api/v3/templates/<template_uuid>/sample/`) that pre-validates a
proposed Direct Send template content edit against Meta's
`message_samples` API BEFORE mutating local state. The endpoint accepts
the same request body as the existing
`PATCH /api/v3/templates/<uuid>/` (`UpdateTemplateContentSerializer`),
translates the validated payload into Meta's wire shape (`type: text`
for body-only or `type: interactive` with `cta_url` / `button` action
for richer payloads), calls Meta with the resolved WABA id, and gates
the local update on the synchronous category verdict. On
`category == "UTILITY"` the endpoint writes a new `Version` row
directly with `status = "APPROVED"` and advances
`Template.current_version` in the same write (the sample API verdict
IS the Direct Send approval signal; the legacy "PENDING until
TemplatesStatusWebhook confirms" transitional state has no operational
purpose for Direct Send dispatches per spec 002's
`Broadcast.build_direct_send_message`); on any non-UTILITY value the
local template is returned UNCHANGED. The endpoint is gated to
Direct-Send-eligible templates only
(`Template.integrated_agent.config["direct_send"] == True`) — the
SAME predicate `Broadcast.build_message` reads at dispatch time per
spec 002's `retail/agents/domains/agent_webhook/services/broadcast.py:932`
— so the "skip PENDING, write APPROVED directly" rule only fires
where the dispatch path actually reads from local `metadata`.

The technical approach (resolved in `./research.md`) is:

1. **New endpoint** on the existing `TemplateViewSet`
   (`retail/templates/views.py`) as a DRF detail action
   `@action(detail=True, methods=["post"]) def sample(...)`. The
   view is thin — it validates input via a new
   `ValidateTemplateSampleSerializer` (a literal subclass of
   `UpdateTemplateContentSerializer` that adds the FR-003a length
   caps + button-mode disjointness check), builds a frozen
   `ValidateTemplateSampleDTO` (`@dataclass(frozen=True)`), delegates
   to the use case, and returns the HTTP response (Constitution
   Principle I — Views layer; FR-001 / FR-002 / FR-003 / FR-003a).
2. **New use case** `ValidateTemplateSampleUseCase` lives under
   `retail/templates/usecases/validate_template_sample.py`. It owns
   the orchestration: load the Template by uuid with
   `select_related("integrated_agent")`, gate on the
   `config["direct_send"]` predicate (FR-002a), resolve the project's
   WABA id from `ProjectOnboarding.config["channels"]["wpp-cloud"]["channel_data"]["waba_id"]`
   (FR-005a), build the Meta wire-shape body via a new pure-function
   translator (FR-004), call
   `MetaService.submit_template_sample(waba_id, body)` (FR-005), and
   branch on Meta's `category` verdict (FR-005b / FR-006). On
   `category == "UTILITY"` the use case invokes the extracted shared
   helpers from `UpdateNormalTemplateStrategy` (see point 4 below)
   with `version_status="APPROVED"` and
   `advance_current_version=True` per FR-006a / FR-006d; on any
   non-UTILITY value the local template is untouched (FR-006b). The
   use case is framework-agnostic (no `rest_framework` imports),
   emits every audit-log line via a private helper that bakes in the
   `[TemplateSampleValidation]` tag (FR-008), and raises
   domain-friendly exceptions (`NotDirectSendEligibleError`,
   `WabaNotConfiguredError`, `MetaSampleUnavailableError`,
   `MetaInvalidResponseError`) that the view translates into the
   HTTP status codes from FR-007 / FR-007a–e.
3. **New pure-function translator** lives at
   `retail/templates/adapters/direct_send_sample_translator.py`. It
   takes the validated DTO and returns the Meta `message_samples`
   wire-shape dict (FR-004 / FR-004a–e). Pure (no DB, no I/O,
   testable without database setup per FR-004d). Reuses
   `substitute_template_variables` from
   `retail.agents.domains.agent_webhook.services.direct_send_payload_builder`
   for the outbound `{{N}}` substitution rule (A7 / FR-004e). The
   IMAGE-header → public URL resolution reuses the existing
   `TemplateMetadataHandler._upload_header_image` (FR-004a / A9) —
   called by the use case BEFORE the translator is invoked, so the
   translator stays I/O-free.
4. **Existing strategy refactor** — extract two private helpers from
   `UpdateNormalTemplateStrategy.update_template` (`retail/templates/strategies/update_template_strategies.py`):
   `_apply_metadata_update(template, payload) -> translation_payload`
   (encapsulates `_update_common_metadata` +
   `template.save(update_fields=["metadata"])` +
   `_sync_abandoned_cart_image_config`) and
   `_create_version_with_options(template, payload, *, status,
   advance_current_version) -> Version` (encapsulates the existing
   `_create_version` plus the optional `current_version` repoint).
   The existing `update_template` composes them as
   `_apply_metadata_update → _create_version_with_options(status="PENDING",
   advance_current_version=False) → _notify_integrations`; the new
   sample endpoint composes
   `_apply_metadata_update → _create_version_with_options(status="APPROVED",
   advance_current_version=True)` and STOPS — no Integrations push
   (FR-006 / FR-006d / A10). The refactor is behavior-preserving for
   the legacy PATCH endpoint: same writes, same Celery task fired,
   same metadata shape, no observable change.
5. **MetaClient + MetaService extension** — add
   `submit_template_sample(waba_id: str, sample_body: Dict[str, Any]) -> Dict[str, Any]`
   to both `MetaClient` (`retail/clients/meta/client.py`) and
   `MetaService` (`retail/services/meta/service.py`), plus their
   Protocol interfaces (`retail/interfaces/clients/meta/client.py`
   and `retail/interfaces/services/meta.py`). The client uses the
   same `_json_headers` / `make_request` plumbing as `create_flow`
   and `register_public_key` against
   `POST {META_API_URL}/{waba_id}/message_samples`. The service
   method PROPAGATES `CustomAPIException` (and any unexpected
   exception) rather than swallowing to `None` — the use case needs
   the raw response body to surface to the frontend per FR-005c.
   This is a documented deviation from the existing
   `fetch_library_template_by_name_and_language` pattern (which
   swallows because its caller treats `None` as "fall through to
   the next strategy"); the deviation is justified by the new
   endpoint's responsibility to translate Meta errors into
   HTTP 502 responses, which requires the raw error envelope.
6. **No new model, no new column, no migration**. The
   `IntegratedAgent.config["direct_send"]` flag was added by spec
   002. The `Project.uuid` and `ProjectOnboarding.config["channels"]["wpp-cloud"]["channel_data"]["waba_id"]`
   paths are pre-existing (`retail/projects/usecases/configure_wpp_cloud.py:96-114`).
   `Version.status = "APPROVED"` is a long-standing enum member
   (`retail/templates/models.py:48-59`). The feature ships zero
   migrations across all apps.
7. **No new Celery task, no new queue**. The new endpoint does NOT
   fire `task_create_template.delay(...)` (FR-006 / A10); Direct
   Send templates do not use the Integrations engine as a content
   source, and firing the push would actively break Direct Send
   dispatch via Meta error 132021 ("A template with the same name
   already exists" per `docs/direct-send-api-beta-integration.md:976`).
   The pattern mirrors `AssignAgentUseCase`'s Direct Send template
   creation at `retail/agents/domains/agent_integration/usecases/assign.py:421-438`,
   which also writes `Version.status = "APPROVED"` locally without
   any Integrations push.

## Technical Context

**Language/Version**: Python 3.10 (`pyproject.toml` `python = "^3.10"`).

**Primary Dependencies**: Django 5.0, Django REST Framework 3.15,
`requests` (transitively via `retail.clients.base.RequestClient` for
the outbound Meta call), `mozilla-django-oidc` (transitively via the
existing `IsAuthenticated` + `HasProjectPermission` view-class auth
chain — no direct OIDC code path is introduced). The feature reuses
the existing `MetaClient` / `MetaService`,
`UpdateNormalTemplateStrategy` / `UpdateCustomTemplateStrategy`,
`TemplateTranslationAdapter`, `TemplateMetadataHandler`,
`TemplateBuilderMixin._create_version`, and
`substitute_template_variables` modules without introducing new
third-party dependencies.

**Storage**: PostgreSQL via `psycopg2`. **Zero schema changes**. No
new column, no new index, no new constraint, no new table. The
single `INSERT` per UTILITY-classified request creates one
`templates_version` row via the existing `_create_version` path
(`weni_<name>_<timestamp>` template_name, same FK linkages), and a
single `UPDATE` advances `templates_template.current_version_id` to
the new row's PK in the same transaction. The metadata rewrite is
a single `UPDATE` on `templates_template.metadata` (JSONField,
unchanged column shape).

**Testing**: `django.test.TestCase` + `unittest.mock` (`MagicMock`,
`patch`). New test files under
`retail/templates/tests/usecases/test_validate_template_sample.py`,
`retail/templates/tests/views/test_validate_template_sample_view.py`,
`retail/templates/tests/adapters/test_direct_send_sample_translator.py`,
and MOD on
`retail/templates/tests/strategies/test_update_template_strategies.py`
to exercise the new extracted helpers. The MetaService /
MetaClient additions get matching test entries in
`retail/services/tests/test_meta.py` (existing file). `coverage`
7.8 + the project's `contrib/compare_coverage.py` parity check.
Direct Send broadcast-renderer parity is verified by an integration
test that fires a UTILITY sample and then triggers
`Broadcast.build_direct_send_message` against the same template,
asserting the rendered payload reflects the new content (US2 /
SC-004).

**Target Platform**: Linux (containerized service, `docker/`). The
endpoint sits behind the existing
`IsAuthenticated + HasProjectPermission` view-class auth chain
(FR-002) — same gate the existing PATCH endpoint uses today. The
outbound Meta call uses the existing `META_API_URL` setting and
`META_SYSTEM_USER_ACCESS_TOKEN` secret; no new env var is
introduced.

**Project Type**: web-service (Django + DRF backend; this feature
adds one POST endpoint to the existing `retail.templates.urls` URL
namespace).

**Performance Goals**:

- Per-request latency: p99 < 3 seconds in steady state (spec
  SC-006). The dominant contributor is the outbound Meta sample
  call (Retail does not control its latency); Retail's local hot
  path is bounded structurally by (a) one Template read with
  `select_related("integrated_agent")`, (b) one `ProjectOnboarding`
  read for the WABA id, (c) optional S3 upload for IMAGE headers
  (FR-004a / A9), (d) the outbound `requests.post` to Meta, and
  (e) on UTILITY only, two single-row writes (Version INSERT +
  Template UPDATE for `metadata` + `current_version`). No Celery
  enqueue is on the hot path (A10).
- Direct Send broadcast renders the new content on the NEXT
  dispatch attempt with NO additional latency budget (SC-004):
  `Template.current_version` is repointed in-line to the new
  `APPROVED` Version, so `Broadcast.build_direct_send_message`
  reads the new row on its very next call.
- The realistic traffic profile is bursty-operator (an operator
  iterating on a content edit submits 1–5 samples per minute
  during the iteration session; steady-state across the fleet is
  ≤10 samples/minute). Throughput is not a release gate and no
  PR-time load test is required.

**Constraints**:

- **Backward compatibility — existing `PATCH /api/v3/templates/<uuid>/` untouched (FR-011, FR-014)**:
  The legacy endpoint continues to operate exactly as today after
  the strategy refactor in point 4 above. The refactor extracts
  two private helpers from `UpdateNormalTemplateStrategy.update_template`
  but recomposes them into the same flow at the same call sites
  — the public surface, the request schema, the response shape,
  the `task_create_template.delay(...)` push, the new Version's
  `PENDING` status, and the lack of `current_version` advance are
  all preserved. The existing test suite at
  `retail/templates/tests/strategies/test_update_template_strategies.py`
  + `retail/templates/tests/usecases/test_update_template_body.py`
  pins this; the refactor adds new tests for the extracted
  helpers without modifying the existing assertions.
- **Pre-existing dispatch gate untouched (FR-012)**: This feature
  writes `Version.status = "APPROVED"` and advances
  `Template.current_version`, but does not modify
  `Broadcast.build_message` or `build_direct_send_message`. Spec
  002's dispatch gate
  (`retail/agents/domains/agent_webhook/services/broadcast.py`)
  already reads `current_version` + `metadata` on every call and
  inherits the new content for free.
- **Pre-existing spec 003 webhook untouched (FR-012)**: The
  category-detection webhook
  (`retail/webhooks/templates/views/direct_send_category.py` +
  `retail/webhooks/templates/usecases/direct_send_category.py`)
  is read-only context. Spec 003's auto-demote channel continues
  to fire on a future `template_correct_category=UTILITY` payload;
  this feature's sample-validation channel is a THIRD recovery
  channel for FLAGGED templates (spec.md §Edge Cases, FR-014 of
  spec 003).
- **Audit log shape pinned to `[TemplateSampleValidation] <event_name>: <k=v> ...` (FR-008)**:
  The closed enumeration of `event_name` tokens is the contract
  surface for operator dashboards (FR-008a). New tokens MAY be
  added in future PRs (additive-only); existing tokens MUST NOT
  be renamed or removed. The log-level discipline mirrors spec
  003's `[DirectSendCategoryWebhook]` channel: INFO for the happy
  path (`received`, `meta_sample_submitted`, `meta_sample_response`,
  `template_updated`, `update_skipped`), WARNING for
  "expected but unhappy" pre-flight refusals
  (`meta_invalid_response`, `waba_not_configured`,
  `not_direct_send_eligible`), ERROR with `exc_info=True` for
  genuine failures only (`meta_error`,
  `local_update_failed_after_meta_approval`).
- **PII redaction in the audit log (FR-008c)**: customer-facing
  draft content (`template_body`, `template_header`,
  `template_footer`, button text values) MUST NOT be logged
  verbatim. The audit log captures length + presence flags only
  (`template_body_len=42`, `template_header_present=true`).
  Identifiers (`template_uuid`, `version_uuid`,
  `integrated_agent_uuid`, `project_uuid`, `app_uuid`, `waba_id`)
  are logged in full.
- **No Integrations push for the new endpoint (FR-006 / A10)**:
  `task_create_template.delay(...)` is structurally absent from
  the new composition (point 4 above STOPs after
  `_create_version_with_options`). This is a behavioral deviation
  from the legacy PATCH endpoint, justified by three reasons
  spelled out in spec.md A10 (dispatch path doesn't consult
  Integrations for Direct Send; firing the push would trigger
  Meta error 132021 conflict; pattern mirrors `AssignAgentUseCase`'s
  Direct Send template creation at `assign.py:421-438`).
- **MetaService raises rather than swallows for the new method (FR-005c)**:
  `MetaService.submit_template_sample` propagates
  `CustomAPIException` and any unexpected exception. This is a
  documented deviation from the existing
  `fetch_library_template_by_name_and_language` pattern (which
  collapses errors to `None`), justified by the new use case's
  responsibility to translate Meta errors into HTTP 502 responses
  with the raw error envelope per FR-007b. The deviation is
  recorded as Decision 5 in `research.md`.
- **No new env var or settings key**: The feature reuses the
  existing `META_API_URL` and `META_SYSTEM_USER_ACCESS_TOKEN`
  settings. Deployment requires zero settings change.

**Scale/Scope**:

- Steady-state request volume: ≤10 samples/minute across the
  entire fleet (bursty per-operator during a content-edit session,
  near-zero between sessions). Each call is dominated by a single
  outbound Meta round-trip; throughput is bounded by Meta's
  per-WABA sample-API quota (FR-005c references Meta error 2388341
  "Samples API Access is restricted" per
  `docs/direct-send-api-beta-integration.md:977`).
- Per-WABA usage: the docs recommend 3–4 samples per business
  onboarding (`docs/direct-send-api-beta-integration.md:569`), so
  the sustained per-WABA rate is operationally bounded by
  iteration cadence — operators submit a small batch of revisions
  per template per day, not continuously.
- Code surface: ~10 files modified or added (4 new production:
  view-action method addition, new use case, new translator, new
  serializer subclass; 4 MOD on existing production:
  `MetaClient`, `MetaService`, `MetaClientInterface`,
  `MetaServiceInterface`, `update_template_strategies.py` helper
  extraction; 4 new test files; one MOD on existing test file for
  the strategy helpers). No new app, no new model, no new
  migration.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1
design. Reference: `.specify/memory/constitution.md` (v1.0.0).*

### I. Layered Clean Architecture (NON-NEGOTIABLE) — PASS

- **Views layer**: The new action on `TemplateViewSet` is a thin
  DRF method. It validates the payload via
  `ValidateTemplateSampleSerializer` (a subclass of
  `UpdateTemplateContentSerializer`), builds a frozen
  `ValidateTemplateSampleDTO`, delegates to the use case, catches
  the use case's domain exceptions and translates them into the
  HTTP responses pinned by FR-007 / FR-007a–e. The action calls
  no `Model.objects.*`, carries no business logic, and imports no
  infrastructure clients. Authorization is expressed exclusively
  via `permission_classes = [IsAuthenticated, HasProjectPermission]`
  inherited from the existing `TemplateViewSet` (no
  `self.check_object_permissions(...)`, no `if request.user...`).
- **Use Cases layer**: `ValidateTemplateSampleUseCase` holds every
  business rule (Direct-Send-eligibility gating, WABA-id
  resolution, conditional update on Meta's verdict, audit-log
  emission), every ORM query (`Template.objects.select_related("integrated_agent").get(uuid=...)`,
  `ProjectOnboarding.objects.filter(project__uuid=...).first()`,
  the strategy-helper writes), and every domain-exception raise.
  Framework-agnostic: no `rest_framework` imports, no
  `Request` / `Response` use, no permission checks.
- **Services layer**: `MetaService.submit_template_sample` is the
  new outbound boundary. Per FR-005c it PROPAGATES exceptions
  (rather than swallowing to `None`) — a documented deviation
  from the existing pattern, justified by the use case's
  responsibility to translate Meta errors into HTTP 502 responses
  with the raw error envelope (Constitution Principle I notes the
  Service layer "catches infrastructure exceptions" and "returns
  `None` on failure"; the constitution's intent is "don't propagate
  raw infrastructure errors UPWARD unmodified" — propagating
  `CustomAPIException` here IS the documented contract, and the
  use case catches it). Recorded as Decision 5 / Complexity
  Tracking row 1 below.
- **Clients layer**: `MetaClient.submit_template_sample` is the
  only outbound HTTP call introduced. It uses the existing
  `make_request` plumbing, the existing `Bearer` auth header
  shape from `_json_headers`, and the existing `CustomAPIException`
  envelope on infrastructure failures. The new method is added to
  the `MetaClientInterface` Protocol so callers depend on the
  interface, not the concrete class.
- **Interfaces layer**: Both `MetaClientInterface` (for the
  client → service boundary) and `MetaServiceInterface` (for the
  service → use case boundary) gain a `submit_template_sample`
  method signature. Structural subtyping via `typing.Protocol`,
  no `@runtime_checkable`.

### II. DRF Composition for AuthN/AuthZ — PASS

- The new action declares `permission_classes` IDENTICAL to the
  existing PATCH path:
  `[IsAuthenticated, HasProjectPermission]`. No new permission
  class is introduced.
- No permission logic appears inside the action method body or
  inside the use case. The use case's `not_direct_send_eligible`
  check (FR-002a) is a domain-level GATE on the resource shape,
  NOT an authorization check — it asks "is this template
  configured for the Direct Send dispatch path", not "is this
  user allowed to access this template". The distinction matches
  the Constitution Principle I separation: domain rules live in
  the use case; permission rules live on the view.
- Both permission classes inherit (transitively or directly) from
  `BasePermission`, so the existing `&` / `|` composition is
  preserved.

### III. Test Coverage Parity & Isolated Tests (NON-NEGOTIABLE) — PASS (with planned tests)

Every new code branch will be exercised by tests in the same PR
(enumerated in `tasks.md`). Notable points:

- **Use case tests**
  (`retail/templates/tests/usecases/test_validate_template_sample.py`):
  cover all FR-008a event-name branches (`received`,
  `meta_sample_submitted`, `meta_sample_response`,
  `template_updated`, `update_skipped`, `meta_error`,
  `meta_invalid_response`, `waba_not_configured`,
  `not_direct_send_eligible`, `local_update_failed_after_meta_approval`).
  The conditional-update gate is pinned by parametrized cells:
  `category == "UTILITY"` triggers the update,
  `category == "MARKETING"` / `category == "AUTHENTICATION"` /
  arbitrary other non-UTILITY value does NOT, missing `category`
  field surfaces as `meta_invalid_response`. The FR-002a gating
  predicate is pinned by three cells: `integrated_agent is None`,
  `integrated_agent.config = {}`,
  `integrated_agent.config = {"direct_send": False}`.
- **View tests**
  (`retail/templates/tests/views/test_validate_template_sample_view.py`):
  cover the HTTP 200 / 400 / 401 / 404 / 500 / 502 boundaries
  (FR-007 / FR-007a–e / FR-007b). The auth gate is exercised by
  sending the request with and without
  `IsAuthenticated + HasProjectPermission`. The serializer
  validation gate is exercised by sending payloads that violate
  the FR-003a length caps and the button-mode disjointness rule.
- **Translator tests**
  (`retail/templates/tests/adapters/test_direct_send_sample_translator.py`):
  pure-function tests covering every wire-shape variant
  (`text`, `interactive.cta_url` with TEXT header,
  `interactive.cta_url` with IMAGE header,
  `interactive.button` with reply buttons), the variable
  substitution rule (FR-004e), the deterministic `reply.id`
  derivation (FR-004c) including duplicate-tiebreaking, the URL
  resolution helper composition (FR-004b) for buttons whose
  `url` is the `{base_url, url_suffix_example}` upstream shape vs
  the already-flat shape.
- **Strategy refactor tests**
  (`retail/templates/tests/strategies/test_update_template_strategies.py`):
  add explicit unit tests for the new extracted helpers
  (`_apply_metadata_update`, `_create_version_with_options`) at
  both call-site shapes
  (`status="PENDING", advance_current_version=False` — legacy
  PATCH composition; `status="APPROVED",
  advance_current_version=True` — sample-validation composition).
  Existing `update_template` assertions must continue to pass
  unchanged — the refactor is behavior-preserving.
- **MetaClient / MetaService tests**
  (`retail/services/tests/test_meta.py` MOD): add a test that
  `MetaService.submit_template_sample` delegates to the client
  and PROPAGATES (does NOT swallow) `CustomAPIException`. The
  existing `fetch_library_template_by_name_and_language` test
  remains unchanged (its swallow behavior is preserved).
- **Integration test**
  (`tasks.md` will name a T-token): fires a UTILITY sample
  against a Direct Send-eligible template, then invokes
  `Broadcast.build_direct_send_message` against the same template
  and asserts the rendered payload reflects the new content. This
  pins SC-004 / US2 without modifying the dispatch path.
- **No `# pragma: no cover` required**: every code branch has a
  finite, in-process exercisable test path. The outbound Meta
  call is mocked at the `MetaService` boundary; no live external
  provider is involved.
- **Cache isolation**: the use case does not touch the Django
  cache, so the `LocMemCache` override pattern is not required
  for this feature's tests beyond what the existing
  `BaseTestMixin` provides for `HasProjectPermission`'s Connect
  proxy calls.

### IV. Self-Documenting Code — PASS

- Method names carry intent
  (`_gate_on_direct_send_eligibility`, `_resolve_waba_id`,
  `_build_meta_sample_body`, `_call_meta_sample_api`,
  `_apply_local_update_on_utility`, `_emit_received`,
  `_emit_meta_sample_submitted`, `_emit_meta_sample_response`,
  `_emit_template_updated`, `_emit_update_skipped`,
  `_emit_meta_error`, `_emit_local_update_failed_after_meta_approval`).
- The `[TemplateSampleValidation]` log helper is the only point
  in the code that knows the log-line shape — every event
  emission routes through it, so the FR-008 format is enforced
  structurally (no
  `logger.info(f"[TemplateSampleValidation] ...")` scattered
  across the codebase).
- Docstrings are reserved for non-obvious *why* (e.g. why the new
  endpoint persists `Version.status = "APPROVED"` directly while
  the legacy PATCH endpoint persists `"PENDING"` — A10 / FR-006d;
  why the IMAGE-header S3 upload runs BEFORE the Meta call — A9;
  why the substituted body is sent outbound but the persisted
  metadata keeps `{{N}}` — A7).
- Logging f-string identifiers always carry the relevant tenant
  + resource identifiers (`project_uuid`, `template_uuid`,
  `integrated_agent_uuid`, `waba_id`). Customer-facing content is
  PII-redacted to length + presence flags per FR-008c.
- Single Level of Abstraction is preserved by the use case's
  helper decomposition: the `execute` method reads as
  `_gate → _resolve_waba_id → _build_body → _call_meta →
   _branch_on_category → _emit_completed` without inline
  formatting or log-string construction.

### V. Conventional Commits & Structured PRs — PASS

- Branch: `004-template-sample-validation` (spec-kit
  numeric-prefix convention auto-generated by the
  `before_specify` git hook, consistent with specs 002 and 003 —
  same trade-off documented as Complexity Tracking row 2 below).
- PR title (≤72 chars): `feat: add Direct Send template sample validation endpoint` (58 chars).
- PR description follows the `## What` / `## Why` template.
- No new model is added by this feature, so the "integer PK +
  `uuid (unique=True)`" pattern for new models (Constitution
  Principle V) does not apply. The existing `Version` /
  `Template` / `IntegratedAgent` / `Project` / `ProjectOnboarding`
  models keep their legacy UUID PKs unchanged.

### Constitution Check verdict

**No violations.** The Complexity Tracking table below records two
non-violation items for auditability: (1) the documented deviation
from the Service-layer "swallow to None" pattern for
`MetaService.submit_template_sample` (Constitution Principle I
guidance), and (2) the spec-kit branch-name convention deviation
from Principle V's `<type>/<kebab>` form (same trade-off as specs
002 and 003).

The Constitution Check was re-evaluated after Phase 1 design
(data-model, contracts, quickstart) and the verdict stands.

## Project Structure

### Documentation (this feature)

```text
specs/004-template-sample-validation/
├── plan.md                                       # This file (/speckit-plan command output)
├── research.md                                   # Phase 0 — design decisions resolved
├── data-model.md                                 # Phase 1 — persisted state changes (zero schema change)
├── contracts/
│   ├── sample-endpoint-request-response.md       # Inbound contract (Frontend → Retail)
│   └── meta-message-samples.md                   # Outbound contract (Retail → Meta)
├── quickstart.md                                 # End-to-end happy-path validation script
├── checklists/
│   └── requirements.md                           # Existing — created during /speckit-specify
├── spec.md                                       # Feature specification (/speckit-specify output)
└── tasks.md                                      # Phase 2 output (NOT created by /speckit-plan)
```

### Source Code (repository root)

The feature adds new files under `retail/templates/` and extends
two existing modules under `retail/clients/meta/` and
`retail/services/meta/`. Files marked **NEW** are added; **MOD** is
modified in place; everything else is read-only context.

```text
retail/
├── templates/
│   ├── views.py                                                              # MOD — add `sample` @action to TemplateViewSet
│   ├── serializers.py                                                        # MOD — add ValidateTemplateSampleSerializer + SampleValidationResponseSerializer
│   ├── exceptions.py                                                         # MOD — add NotDirectSendEligibleError, WabaNotConfiguredError, MetaSampleUnavailableError, MetaInvalidResponseError
│   ├── usecases/
│   │   ├── validate_template_sample.py                                       # NEW — DTO + UseCase + Result + audit-log helper
│   │   └── update_template_body.py                                           # untouched (legacy PATCH endpoint use case)
│   ├── strategies/
│   │   └── update_template_strategies.py                                     # MOD — extract _apply_metadata_update + _create_version_with_options helpers; recompose update_template to call them
│   ├── adapters/
│   │   └── direct_send_sample_translator.py                                  # NEW — pure-function module that converts the validated DTO to Meta's message_samples wire shape
│   └── tests/
│       ├── usecases/
│       │   └── test_validate_template_sample.py                              # NEW — unit tests for ValidateTemplateSampleUseCase
│       ├── views/
│       │   └── test_validate_template_sample_view.py                         # NEW — view tests (auth, payload shape, HTTP boundary)
│       ├── adapters/
│       │   └── test_direct_send_sample_translator.py                         # NEW — pure-function tests for the wire-shape translator
│       └── strategies/
│           └── test_update_template_strategies.py                            # MOD — add tests for the new extracted helpers
├── clients/
│   └── meta/
│       └── client.py                                                         # MOD — add submit_template_sample method on MetaClient
├── services/
│   ├── meta/
│   │   └── service.py                                                        # MOD — add submit_template_sample method on MetaService (propagates CustomAPIException)
│   └── tests/
│       └── test_meta.py                                                      # MOD — add tests for submit_template_sample (propagation behavior)
└── interfaces/
    ├── clients/
    │   └── meta/
    │       └── client.py                                                     # MOD — add submit_template_sample to MetaClientInterface Protocol
    └── services/
        └── meta.py                                                           # MOD — add submit_template_sample to MetaServiceInterface Protocol
```

**Structure Decision**: the feature lands as an additive extension
to the existing `retail/templates/` namespace, mirroring the
existing `TemplateViewSet`'s file layout (`views.py`,
`serializers.py`, `usecases/<name>.py`,
`adapters/<name>.py`, `strategies/<name>.py`, `tests/<sub>/test_<name>.py`).
The choice keeps the new endpoint discoverable alongside the
existing `PATCH /api/v3/templates/<uuid>/` it composes with, which
matches the spec's FR-001 placement rule and the existing operator
mental model for "template CRUD". No new app is introduced; no new
top-level package is created.

The Meta-side changes (`MetaClient`, `MetaService`, their
interfaces) extend the existing `retail/clients/meta/`,
`retail/services/meta/`, `retail/interfaces/clients/meta/`,
`retail/interfaces/services/meta.py` modules in place — same
precedent as spec 002's broadcast-renderer additions on `Broadcast`
(no new client / service / interface was introduced there either).
The new `MetaService.submit_template_sample` method is added next
to `create_flow` / `register_public_key` / `publish_flow` in
`MetaService`, preserving the file's "one method per Meta endpoint
Retail calls" organizing principle.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations. The two items below are recorded for
auditability — one documented deviation from a Service-layer
convention (the new method propagates rather than swallows) and
one workflow-driven branch-name deviation from Principle V (same
precedent as specs 002 and 003).

| Issue | Why it is acceptable | Simpler alternative rejected because |
|-------|----------------------|--------------------------------------|
| `MetaService.submit_template_sample` PROPAGATES `CustomAPIException` (and any unexpected exception) to its caller rather than catching, logging, and returning `None` (the pattern used by every other `MetaService` method — `fetch_library_template_by_name_and_language`, `create_flow`, `register_public_key`, `publish_flow`). | Per FR-005c the use case MUST surface the raw Meta error envelope (HTTP status code, Meta error code, Meta error message) to the frontend as part of the `meta_sample_response` field on the HTTP 502 body. The existing swallow pattern collapses error context to a single `None` sentinel, which would force the use case to either (a) read the logged error back from the log stream (anti-pattern; tight coupling to log shape) or (b) re-call Meta to retrieve the same error (anti-pattern; double-charges the quota). Propagating the exception is the documented contract for this method and is captured as Decision 5 in `research.md`. The use case catches the exception at a single point and translates it to the domain exception `MetaSampleUnavailableError`, so the propagation does NOT leak `requests.exceptions` or `CustomAPIException` upward to the view — the view sees only the domain exception. The existing `MetaService` methods retain their swallow behavior (no behavioral change). | Forcing the new method to swallow would require either log-replay parsing (brittle and tightly coupled to log shape) or a double-call to Meta (wastes quota, double-charges latency, and Meta's `2388341 — Samples API Access is restricted` error is the very thing we need to surface — re-calling on a restricted account would still get the same error but burns one more sample-quota slot). |
| Branch name is `004-template-sample-validation` (spec-kit numeric-prefix convention) rather than the Constitution Principle V form `feature/<kebab-description>`. | The numeric-prefix form is created automatically by the spec-kit `before_specify` git hook (`.specify/extensions.yml`) and is the convention documented in `docs/SPEC_KIT.md` for every spec-driven feature in this repo (precedents: spec 002's `002-direct-send-broadcasts` and spec 003's `003-template-category-webhook`, both with the same trade-off accepted in their respective `Complexity Tracking` sections). Reusing the auto-generated branch keeps the spec-kit artifacts, the git history, and the PR metadata co-located under a single identifier (`004-…`). | Renaming the branch to `feature/template-sample-validation` mid-feature would break the spec-kit tooling's branch ↔ `specs/<id>/` association and force a manual rename of every cross-reference in `spec.md` / `plan.md` / `tasks.md` / artifact tables. A constitution amendment to formally codify the spec-kit exemption is a separate, repo-wide change that does not belong in this feature's PR. |
