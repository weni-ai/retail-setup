---

description: "Task list for the Template Sample Validation Endpoint for Direct Send feature"
---

# Tasks: Template Sample Validation Endpoint for Direct Send

**Input**: Design documents from `/specs/004-template-sample-validation/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/sample-endpoint-request-response.md`, `contracts/meta-message-samples.md`, `quickstart.md`

**Tests**: Tests are REQUIRED for this feature. The Constitution's Principle III (Test Coverage Parity & Isolated Tests) is NON-NEGOTIABLE — every new branch added by this PR is exercised by a unit or integration test in the same PR, verified by `poetry run coverage run manage.py test && poetry run python contrib/compare_coverage.py`.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested independently. Foundational tasks (Phase 2) provide the building blocks every user story consumes; US1 (Phase 3) wires them into the happy path; US2 / US3 / US4 layer on schema-parity assertions, failure-path coverage, and response-shape verification respectively.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4). No story label on Setup / Foundational / Polish phase tasks.
- Each task includes the exact file path it touches and a short verification cue.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm baseline state before edits.

- [ ] T001 Confirm working tree is on branch `004-template-sample-validation` and the existing test suite is green. Run `git branch --show-current` and `poetry run python manage.py test retail.templates retail.services.tests.test_meta retail.agents.domains.agent_webhook` — expect zero failures. No new dependencies, env vars, apps, or directories are introduced by this feature (per `plan.md` Constraints section), so setup is verification-only.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The pure-function building blocks every user story needs. None of these tasks have observable HTTP behavior on their own — they are scaffolding that US1 (Phase 3) composes into the endpoint orchestration.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

- [ ] T002 [P] Add four new domain exception classes to `retail/templates/exceptions.py`: `NotDirectSendEligibleError`, `WabaNotConfiguredError`, `MetaSampleUnavailableError(message, *, status_code=None, meta_response=None)`, `MetaInvalidResponseError(message, *, meta_response)`. The last two carry the Meta error envelope as a constructor kwarg so the view can include it in the HTTP 502 body per FR-007b. Each class is a simple `Exception` subclass with a docstring naming the FR that mandates it.

- [ ] T003 [P] Extend the `MetaClientInterface` Protocol at `retail/interfaces/clients/meta/client.py` with a `submit_template_sample(self, waba_id: str, sample_body: Dict[str, Any]) -> Dict[str, Any]: ...` method signature. Follow the existing structural-subtyping convention (no `@runtime_checkable`).

- [ ] T004 [P] Extend the `MetaServiceInterface` Protocol at `retail/interfaces/services/meta.py` with a `submit_template_sample(self, waba_id: str, sample_body: Dict[str, Any]) -> Dict[str, Any]: ...` method signature. Add a docstring noting that this method PROPAGATES `CustomAPIException` and unexpected exceptions (does NOT swallow to `None`) per Research Decision 5 / `plan.md` Complexity Tracking row 1, so callers can surface raw Meta error envelopes to HTTP 502 responses.

- [ ] T005 Implement `MetaClient.submit_template_sample(self, waba_id, sample_body)` in `retail/clients/meta/client.py`. POSTs to `f"{self.url}/{waba_id}/message_samples"` with `headers=self._json_headers` and `json=sample_body` via `self.make_request(...)`. Returns `response.json()`. Add a docstring referencing `docs/direct-send-api-beta-integration.md:567-685` and the contract document `contracts/meta-message-samples.md`. (Depends on T003.)

- [ ] T006 Implement `MetaService.submit_template_sample(self, waba_id, sample_body)` in `retail/services/meta/service.py`. DELEGATES directly to `self.client.submit_template_sample(waba_id, sample_body)` and returns the raw response. Does NOT wrap in `try/except` — `CustomAPIException` and any unexpected exception propagate UNMODIFIED to the caller (Research Decision 5). Docstring MUST explicitly call out this propagation deviation from the existing `fetch_library_template_by_name_and_language` pattern, citing the use case's need to surface raw Meta error envelopes to HTTP 502 responses. (Depends on T004 + T005.)

- [ ] T007 Add tests for `MetaService.submit_template_sample` in `retail/services/tests/test_meta.py` (existing file, MOD). Three test cases: (a) happy path returns the body the client returned, (b) `CustomAPIException` raised by the client propagates unmodified (asserts `with self.assertRaises(CustomAPIException)`), (c) an unexpected `Exception` raised by the client also propagates unmodified. Mirror the existing test patterns at `retail/services/tests/test_meta.py:14-83`. (Depends on T006.)

- [ ] T008 Refactor `UpdateNormalTemplateStrategy` (and its parent `UpdateTemplateStrategy` where appropriate) in `retail/templates/strategies/update_template_strategies.py` to extract TWO new private helpers per Research Decision 4 / `data-model.md` §2: `_apply_metadata_update(self, template, payload) -> Dict[str, Any]` (encapsulates `_update_common_metadata` + `template.save(update_fields=["metadata"])` + `_sync_abandoned_cart_image_config` and returns the `translation_payload` dict) and `_create_version_with_options(self, template, payload, *, status: str, advance_current_version: bool) -> Version` (encapsulates the existing `_create_version` call plus an optional `version.status = status; version.save(update_fields=["status"])` write when `status != "PENDING"`, plus an optional `template.current_version = version; template.save(update_fields=["current_version"])` write when `advance_current_version is True`). Recompose `update_template` to call `_apply_metadata_update` → `_create_version_with_options(status="PENDING", advance_current_version=False)` → `_notify_integrations`. The refactor MUST be byte-identical for the legacy PATCH endpoint — every existing assertion in `retail/templates/tests/strategies/test_update_template_strategies.py` and `retail/templates/tests/usecases/test_update_template_body.py` MUST continue to pass without modification. Run those two test files at the end of the task to verify.

- [ ] T009 Add tests for the new extracted helpers in `retail/templates/tests/strategies/test_update_template_strategies.py` (existing file, MOD). Six test cases covering both helpers across the two call-site shapes: (a) `_apply_metadata_update` writes `template.metadata`, returns the translation_payload, and fires `_sync_abandoned_cart_image_config` (when the template's agent matches `settings.ABANDONED_CART_AGENT_UUID`); (b) `_create_version_with_options(status="PENDING", advance_current_version=False)` creates a Version row with default-PENDING status and leaves `template.current_version` unchanged (legacy PATCH composition); (c) `_create_version_with_options(status="APPROVED", advance_current_version=True)` creates a Version row with `status="APPROVED"` and advances `template.current_version` to the new row (sample-validation composition); (d) the previously-current Version is retained in `template.versions.all()` after the advance; (e) the new helper's writes use `update_fields=["status"]` and `update_fields=["current_version"]` respectively (verified by patching `Version.save` and `Template.save` to record `update_fields`); (f) regression — `update_template` still composes both helpers and fires `_notify_integrations` at the end (this test pins the byte-identical-behavior guarantee for the legacy PATCH endpoint). (Depends on T008.)

- [ ] T010 [P] Create the pure-function translator module at `retail/templates/adapters/direct_send_sample_translator.py` per Research Decision 6 / FR-004 / FR-004a–e. Expose ONE public function: `build_meta_sample_body(dto: "ValidateTemplateSampleDTO", *, resolved_header_url: Optional[str] = None) -> Dict[str, Any]`. Implementation: (1) extract variable substitution dict from `dto.template_body_params` keyed by string indices (`{"1": "...", "2": "..."}`) — this is the substitution source per FR-004e / Research Decision 9 (the `parameters` field is NOT consulted); (2) dispatch on payload shape — body-only → `text` wire shape; single `URL`-type button → `interactive.cta_url` wire shape (FR-004 / FR-004b); 1–3 `QUICK_REPLY`-type buttons → `interactive.button` wire shape (FR-004 / FR-004c); (3) for the header sub-object, dispatch on header content — TEXT → `{"type": "text", "text": <substituted>}`; IMAGE → `{"type": "image", "image": {"link": resolved_header_url}}` (FR-004a — the caller resolves base64 → S3 BEFORE calling this function, per A9 / Research Decision 6); (4) substitute every `{{N}}` placeholder in body / header text / footer / each button's `text` / each URL button's `url` using `substitute_template_variables` from `retail.agents.domains.agent_webhook.services.direct_send_payload_builder` (FR-004e); (5) for CTA URL buttons, resolve the URL via `ensure_protocol` + `append_placeholder_if_needed` + `normalize_url_if_needed` from `retail.templates.adapters.url_normalization` per FR-004b; (6) derive each reply button's `id` deterministically from its `text` per FR-004c (lowercase → strip non-alphanum to underscore → collapse consecutive underscores → strip leading/trailing underscores → truncate to 64 chars per `contracts/meta-message-samples.md` "Deterministic reply.id derivation" — 64 leaves headroom for the positional-suffix tiebreaker and keeps logs tidy; on duplicate-within-payload, append `_2` / `_3` positional suffix). The function MUST be pure — no DB access, no I/O, testable without database setup per FR-004d.

- [ ] T011 [P] Add tests for the translator at `retail/templates/tests/adapters/test_direct_send_sample_translator.py` (NEW file). At minimum eleven test cases: (a) body-only payload produces `{"type": "text", "text": {"body": "<substituted>"}}`; (b) CTA URL payload with TEXT header produces the full Shape 2 wire body with `interactive.header.type="text"`; (c) CTA URL payload with `resolved_header_url` produces `interactive.header={"type":"image","image":{"link":"<url>"}}`; (d) CTA URL payload with `url: {base_url, url_suffix_example}` resolves to a flat string with `{{1}}` placeholder appended and `template_body_params[0]` substituted in; (e) CTA URL payload with pre-flat `url: "https://x/{{1}}"` is preserved verbatim through `_is_button_format_already_translated`'s detection; (f) reply buttons payload with 1 button produces Shape 3 with a single `action.buttons[0]`; (g) reply buttons payload with 3 buttons produces three `action.buttons` entries; (h) reply buttons with duplicate `text` values produce distinct `reply.id` values via the `_2` / `_3` suffix rule (and the base `id` does not exceed 64 chars per Research Decision 6's truncation cap); (i) variable substitution fires on body + header text + footer + button text + button URL (parametrize across the four shapes); (j) missing-index substitution substitutes to empty string and emits a WARNING log line (per FR-004e); (k) `parameters=[{"name":"role","value":"manager"}]` payload is processed but the wire body does NOT contain `"manager"` anywhere (Research Decision 9 — `parameters` is NOT a substitution source). Pure-function tests — no Django `TestCase` boilerplate needed; use plain `unittest.TestCase` or pytest-style assertions.

- [ ] T012 [P] Add `ValidateTemplateSampleSerializer` to `retail/templates/serializers.py`. Subclass `UpdateTemplateContentSerializer` (so the field set is byte-for-byte compatible per FR-003 / FR-014). Add the FR-003a length-cap + button-mode disjointness validations: `template_body` max_length=1024; `template_footer` max_length=60; per-button `text` ≤ 20 chars; `template_button` MUST contain either ≤1 URL-type entries OR ≤3 QUICK_REPLY-type entries, never both; `template_header` ≤ 60 chars ONLY when the value looks like plain text (not an HTTP(S) URL, not a base64 data URI, not an existing S3 URL — apply the `_is_image_url` / `_is_base_64` / `_is_s3_url` heuristics already used by `HeaderTransformer` and `TemplateMetadataHandler`). Place validation logic in `validate_template_body`, `validate_template_header`, `validate_template_footer`, `validate_template_button` methods (DRF idiom). Additionally, add a `validate_project_uuid(self, value)` method per FR-002b / Research Decision 11: read `request = self.context.get("request")`, compare `request.headers.get("Project-Uuid")` against `value`, and raise `serializers.ValidationError("Project-Uuid header does not match body project_uuid", code="project_uuid_mismatch")` on mismatch. The view MUST instantiate this serializer with `context={"request": request}` for the read to work — T016 covers that wiring. Constitution Principle IV: prefer extracting helper functions over inline narrative comments.

- [ ] T013 [P] Add serializer tests in `retail/templates/tests/serializers/test_template_serializers.py` (existing file, MOD). Test cases: (a) body at exactly 1024 chars passes, body at 1025 chars fails with field-level error; (b) TEXT header at exactly 60 chars passes, TEXT header at 61 chars fails; (c) IMAGE-URL header longer than 60 chars passes (cap applies only to TEXT); (d) base64-data-URI header longer than 60 chars passes; (e) footer at 60 chars passes, 61 chars fails; (f) one button with 20-char text passes; one button with 21-char text fails; (g) one URL button passes; two URL buttons fail; (h) three QUICK_REPLY buttons pass; four QUICK_REPLY buttons fail; (i) one URL + one QUICK_REPLY (mixed) fails with `"Cannot mix URL and QUICK_REPLY buttons in a single sample."`; (j) inherited validation — payload with no body / header / footer fails with the inherited error message; (k) FR-002b — `context={"request": <req_with_header>}` where `Project-Uuid` header equals `project_uuid` body: passes; (l) FR-002b — header differs from body: fails with field-level error `"Project-Uuid header does not match body project_uuid"` and code `project_uuid_mismatch`; (m) FR-002b — header is absent (no `Project-Uuid` provided): the serializer-layer check is skipped (the view's `HasProjectPermission` would have refused earlier; this test verifies the check is permissive when the header is absent so unit tests can be written without forging an HTTP request). (Depends on T012.)

- [ ] T014 [P] Define the in-memory data classes in `retail/templates/usecases/validate_template_sample.py` (NEW file). Add: `ValidateTemplateSampleDTO` as a frozen dataclass carrying the 9 validated input fields per `data-model.md` §7; `ValidateTemplateSampleResult` as a frozen dataclass with `category: str`, `template_updated: bool`, `template: Template`, `meta_sample_response: Dict[str, Any]` plus a `to_dict()` method that delegates to `ReadTemplateSerializer(self.template).data` for the `template` field; `EventName` enum subclassing `(str, Enum)` with the 11 tokens from FR-008a (`received`, `meta_sample_submitted`, `meta_sample_response`, `template_updated`, `update_skipped`, `meta_error`, `meta_invalid_response`, `waba_not_configured`, `not_direct_send_eligible`, `project_uuid_mismatch`, `local_update_failed_after_meta_approval`); `MetaSampleType` enum subclassing `(str, Enum)` with `TEXT`, `INTERACTIVE_CTA_URL`, `INTERACTIVE_BUTTON` per `data-model.md` §7. No `execute` logic yet — that lands in T015.

**Checkpoint**: Foundation ready — every building block (exceptions, Meta client + service, strategy helpers, translator, serializer, DTOs / enums) is in place. The endpoint is NOT yet wired up. User-story work can now begin.

---

## Phase 3: User Story 1 - Operator validates a content edit against Meta before mutating the local template (Priority: P1) 🎯 MVP

**Goal**: Implement the happy-path orchestration for the new endpoint. After this phase, an operator can POST a body / header / footer / button edit to `POST /api/v3/templates/<uuid>/sample/`, have Retail call Meta's `message_samples` API, and (a) on UTILITY classification see the template's local `metadata` + new `Version` + `current_version` written with `status="APPROVED"` plus an HTTP 200 response, or (b) on non-UTILITY classification see the local template unchanged plus an HTTP 200 response carrying the verdict.

**Independent Test**: Per spec.md US1 — submit a UTILITY-classifying body edit to a Direct Send-eligible template and verify (a) HTTP 200 with `{"category":"UTILITY","template_updated":true,...}`, (b) `Template.metadata.body` is rewritten, (c) a new `Version` row exists with `status="APPROVED"`, (d) `Template.current_version` points to it. Repeat with a MARKETING-classifying edit and verify `template_updated:false`, no metadata rewrite, no new Version row.

### Implementation for User Story 1

- [ ] T015 [US1] Implement `ValidateTemplateSampleUseCase.execute(dto)` and its private helpers in `retail/templates/usecases/validate_template_sample.py`. **Pre-condition**: the serializer-layer FR-002b check (T012) has already verified `header Project-Uuid == body project_uuid`, so the use case treats `dto.project_uuid` as the verified, trusted tenant identifier. The use case does NOT re-check the header (the serializer is the single point of enforcement). Inject dependencies via `__init__` with `Optional` parameters that default to concrete instances (Constitution Principle I): `meta_service: Optional[MetaServiceInterface] = None`, `strategy: Optional[UpdateNormalTemplateStrategy] = None` (or the factory + selector pattern matching `UpdateTemplateContentUseCase`). Wire the orchestration per `data-model.md` §9 (sequencing summary): (1) `_emit RECEIVED` carrying `project_uuid`, `app_uuid`, `template_uuid`, `template_body_len`, `template_header_present`, `template_footer_present`, `buttons_count` (PII-redacted per FR-008c); (2) load `Template.objects.select_related("integrated_agent").get(uuid=dto.template_uuid)` — propagate `Template.DoesNotExist` to the view (translates to HTTP 404 via DRF default per FR-011); (3) `_gate_on_direct_send_eligibility(template)` — raise `NotDirectSendEligibleError` if `template.integrated_agent is None` OR `template.integrated_agent.config.get("direct_send", False)` is falsy (FR-002a / `data-model.md` §4); (4) `_resolve_waba_id(dto.project_uuid)` — read `ProjectOnboarding.objects.filter(project__uuid=...).first()`, traverse `config["channels"]["wpp-cloud"]["channel_data"]["waba_id"]`, raise `WabaNotConfiguredError` on any missing-or-empty step (FR-005a / `data-model.md` §3); (5) for IMAGE base64 headers, call `TemplateMetadataHandler._upload_header_image(...)` to get the S3 URL BEFORE invoking the translator (FR-004a / A9); (6) call `build_meta_sample_body(dto, resolved_header_url=...)` from the new translator module; (7) `_emit META_SAMPLE_SUBMITTED` carrying `waba_id`, `template_uuid`, and the inferred `MetaSampleType` (`text` / `interactive.cta_url` / `interactive.button`); (8) call `MetaService.submit_template_sample(waba_id, sample_body)` wrapped in `try/except CustomAPIException as exc` — on exception raise `MetaSampleUnavailableError(..., status_code=exc.status_code, meta_response=getattr(exc, "response_body", None))` and `_emit META_ERROR` with `exc_info=True` (FR-005c / FR-008a / FR-008b); also wrap in a broader `try/except Exception` for unexpected errors that raises the same `MetaSampleUnavailableError` with no `meta_response`; (9) `_emit META_SAMPLE_RESPONSE` carrying the parsed `category`, `success` flag, and HTTP status; (10) extract `category = meta_response.get("category")` — if missing/null/empty OR `meta_response.get("success") is False`, raise `MetaInvalidResponseError(..., meta_response=meta_response)` and `_emit META_INVALID_RESPONSE` (FR-005b / FR-005c); (11) branch on `category == "UTILITY"` — TRUE path: call `strategy._apply_metadata_update(template, payload)` then `strategy._create_version_with_options(template, payload, status="APPROVED", advance_current_version=True)` (FR-006 / FR-006a / FR-006d), capture `previous_current_version_uuid` and `previous_current_version_status` BEFORE the advance for the audit log, then refresh the template (`template.refresh_from_db()`) so the result carries the up-to-date `current_version` FK; `_emit TEMPLATE_UPDATED` with the previous + new version fields per `data-model.md` §1 audit-log fields; FALSE path: `_emit UPDATE_SKIPPED` with `category=<non_utility_value>`; (12) catch any exception that fires DURING the local update (between step 11's strategy calls and the `_emit TEMPLATE_UPDATED`) — `_emit LOCAL_UPDATE_FAILED_AFTER_META_APPROVAL` with `exc_info=True` and re-raise unmodified so DRF's default 500-response fires (FR-006c). Return `ValidateTemplateSampleResult(category=..., template_updated=..., template=..., meta_sample_response=...)`. Private `_emit(event, level, **kv)` helper builds the `[TemplateSampleValidation] <event>: k=v ...` log line in ONE place per FR-008 / spec 003's precedent at `retail/webhooks/templates/usecases/direct_send_category.py:251-273`. PII-redaction (FR-008c) is enforced INSIDE `_emit` — content fields are passed pre-redacted by callers (lengths + presence flags). Constitution Principle IV: helpers carry intent (`_gate_on_direct_send_eligibility`, `_resolve_waba_id`, `_call_meta_sample_api`, `_apply_local_update_on_utility`, `_emit_received`, `_emit_template_updated`, etc.) — no inline string formatting; SLAP preserved.

- [ ] T016 [US1] Add the `sample` DRF action to `TemplateViewSet` in `retail/templates/views.py`. Decorator: `@action(detail=True, methods=["post"])` named `sample` so the auto-generated router URL is `POST /api/v3/templates/<pk>/sample/`. Method body: instantiate `ValidateTemplateSampleSerializer(data=request.data, context={"request": request})` (the explicit `context` kwarg is REQUIRED so the serializer's FR-002b `validate_project_uuid` method can read `request.headers["Project-Uuid"]` — Research Decision 11), call `is_valid(raise_exception=True)`. If the serializer raises a `ValidationError` whose `code` is `project_uuid_mismatch` (FR-002b / FR-007f), the view MUST emit a WARNING-level audit-log line `[TemplateSampleValidation] project_uuid_mismatch: header_project_uuid=<a> body_project_uuid=<b> template_uuid=<pk>` BEFORE re-raising the DRF default 400 response — this preserves the FR-008a `project_uuid_mismatch` event-name token. Build `ValidateTemplateSampleDTO` from the validated_data + the `pk` path param (cast to `str`), instantiate `ValidateTemplateSampleUseCase()`, call `use_case.execute(dto)` inside a `try/except` that translates each of the four domain exceptions per FR-007e / FR-007d / FR-007b: `NotDirectSendEligibleError` → HTTP 400 `{"detail": "Template is not Direct Send-eligible", "error_code": "not_direct_send_eligible"}`; `WabaNotConfiguredError` → HTTP 400 `{"detail": "WABA not configured for this project", "error_code": "waba_not_configured"}`; `MetaSampleUnavailableError` → HTTP 502 `{"detail": "Meta sample submission failed", "error_code": "meta_unavailable"}` (include `meta_response` field when `exc.meta_response is not None`); `MetaInvalidResponseError` → HTTP 502 `{"detail": "Meta did not return a category", "error_code": "meta_invalid_response", "meta_response": exc.meta_response}`. On success return `Response(result.to_dict(), status=status.HTTP_200_OK)`. The ViewSet's existing `permission_classes = [IsAuthenticated, HasProjectPermission]` is inherited automatically (FR-002). No `urls.py` edit is required — DRF's `DefaultRouter` auto-generates the path from the `@action(detail=True)` declaration (Research Decision 1). (Depends on T012, T014, T015.)

- [ ] T017 [P] [US1] Add use-case unit tests in `retail/templates/tests/usecases/test_validate_template_sample.py` (NEW file). Cover the happy paths per US1 acceptance scenarios: (a) body-only UTILITY edit on a Direct Send-eligible template — asserts new Version with `status="APPROVED"`, `Template.current_version` advanced, `Template.metadata.body` rewritten with raw `{{N}}` placeholders preserved (A7), result.`template_updated == True`, audit-log sequence `received → meta_sample_submitted → meta_sample_response → template_updated` AND each event was emitted at the FR-008b-mandated level (`received` / `meta_sample_submitted` / `meta_sample_response` / `template_updated` all INFO) via `with self.assertLogs("retail.templates.usecases.validate_template_sample", level="INFO") as cm:`; (b) same payload with TEXT header + footer + CTA URL button — asserts `Template.metadata.buttons[0]` in canonical local shape (matching `UpdateNormalTemplateStrategy → TemplateTranslationAdapter` output); (c) same payload with IMAGE base64 header — asserts `TemplateMetadataHandler._upload_header_image` was called BEFORE `MetaService.submit_template_sample`, the wire body's `interactive.header.image.link` is the resolved S3 URL, and the persisted `metadata.header.text` is the same S3 URL (A9); (d) reply buttons payload — asserts the wire body's `interactive.action.buttons[i].reply.id` is deterministic per FR-004c; (e) MARKETING classification — asserts no local mutation, no new Version row, `Template.current_version` unchanged, result.`template_updated == False`, audit-log ends in `update_skipped` (INFO level); (f) AUTHENTICATION classification — same as MARKETING; (g) arbitrary unknown non-UTILITY category (e.g. `"PROMO"`) — same as MARKETING (FR-005b's catch-all); (h) byte-for-byte identical resubmission (C5 from speckit-analyze) — submit content that matches `Template.metadata` verbatim, mock Meta to return UTILITY, assert Meta WAS called (no client-side dedup) and a NEW `Version` row WAS created, `Template.current_version` advances to it, and the previous current_version is retained in `Template.versions` history (spec Edge Case "Operator submits a sample whose content is BYTE-FOR-BYTE identical"); (i) `Project.is_blocked == True` (C15 from speckit-analyze) — submit a UTILITY-classifying payload, assert the use case still processes normally, the local update fires, and the result mirrors the (a) happy path (spec Edge Case "Project is `is_blocked=True`" — blocking gates customer deliveries, not validation flows). Use `MagicMock` to inject the Meta service and assert call shapes; use Django `TestCase` for DB setup. The MetaService boundary is the mock surface — no live external provider call is made per Constitution Principle III.

- [ ] T018 [P] [US1] Add view tests in `retail/templates/tests/views/test_validate_template_sample_view.py` (NEW file). Cover the HTTP boundary per US1 + US4 acceptance scenarios + the auth surface: (a) HTTP 200 on UTILITY — response body has exactly four top-level keys `{category, template_updated, template, meta_sample_response}`; `template` conforms to `ReadTemplateSerializer.data` schema (every field present); `template.status == "APPROVED"` per FR-006d; (b) HTTP 200 on MARKETING — same wrapper shape with `template_updated:false` and the UNCHANGED template; (c) HTTP 401 for an unauthenticated request (no JWT); (d) HTTP 403 for a missing / wrong `Project-Uuid` header (no project permission); (e) HTTP 404 for a non-existent `template_uuid` path param (DRF default `NotFound`); (f) HTTP 400 for a serializer-level violation — submit `template_body` over 1024 chars and verify field-level error body per `contracts/sample-endpoint-request-response.md` §"Validation rules"; (g) HTTP 400 / `project_uuid_mismatch` (FR-002b / FR-007f) — submit with `Project-Uuid` header for project A but body `project_uuid` for project B; expect the wrapper `{"detail": "Project-Uuid header does not match body project_uuid", "error_code": "project_uuid_mismatch"}` AND a WARNING-level audit-log line `[TemplateSampleValidation] project_uuid_mismatch: header_project_uuid=... body_project_uuid=... template_uuid=...` was emitted (per T016); the use case MUST NOT be invoked (mocked `MetaService.submit_template_sample` is `assert_not_called()`) and no Meta call is made; (h) verify the view passes `context={"request": request}` correctly by asserting (g) above produces the mismatch error (would silently fail with a missing context — this assertion structurally pins the wiring). Use `BaseTestMixin.setup_internal_user_permissions` and the Connect-proxy mock pattern that the existing `retail/templates/tests/views/test_template_viewset.py` already uses (read it for the auth-setup precedent). (Depends on T015, T016.)

**Checkpoint**: At this point, US1 is fully functional and testable independently. An operator can submit a sample and see UTILITY → local update applied with APPROVED status / MARKETING → no local update. This is the MVP slice; STOP and validate before moving to US2 / US3 / US4 which layer on additional assurances.

---

## Phase 4: User Story 2 - Local content stays in lockstep with what the Direct Send broadcast renders (Priority: P1)

**Goal**: Pin the schema-parity guarantee between this endpoint's writes and the Direct Send broadcast renderer. After this phase, an integration test proves that a UTILITY-classified sample submission produces local state which `Broadcast.build_direct_send_message` renders correctly on the next dispatch, with the new content visible at the very next broadcast attempt (no cache lag, no asynchronous Integrations convergence window).

**Independent Test**: Per spec.md US2 — submit a UTILITY-classifying edit to a Direct Send-eligible template, then invoke `Broadcast.build_direct_send_message` against the same template and assert the rendered payload (`msg.text`, `msg.header`, `msg.cta_message`, `msg.quick_replies`, `msg.direct_send_template_name`) reflects the NEW content with dispatch-time variables substituted.

### Implementation for User Story 2

- [ ] T019 [P] [US2] Add a broadcast-renderer integration test at `retail/templates/tests/usecases/test_validate_template_sample_broadcast_parity.py` (NEW file). Setup: create a Direct Send-eligible IntegratedAgent + Template + initial APPROVED Version (mirroring `AssignAgentUseCase`'s output shape). Action: invoke `ValidateTemplateSampleUseCase` with a UTILITY-mocked Meta response carrying body + header + CTA URL button changes; then invoke `Broadcast().build_direct_send_message(data=..., channel_uuid=..., project_uuid=..., template=template, integrated_agent=integrated_agent)` against the same template (`template.refresh_from_db()` between calls to pick up the in-line `current_version` advance). Assertions: (a) `message["msg"]["text"]` contains the new body with dispatch-time `template_variables` substituted (not the sample-time `template_body_params`); (b) `message["msg"]["header"]` matches the new header shape (`{"type":"text","text":"<substituted>"}` for TEXT or `{"type":"image","image_url":"<s3_url>"}` for IMAGE); (c) `message["msg"]["cta_message"]` has the new `display_text` and `url` (post `{{1}}` substitution); (d) `message["msg"]["direct_send_template_name"]` equals the NEW Version's `template_name` (NOT the baseline's). This pins SC-004.

- [ ] T020 [P] [US2] Add a metadata-shape-parity test (NEW or extend `test_validate_template_sample.py`). Set up two identical input payloads, submit one through the new sample endpoint with a UTILITY-mocked Meta response, and submit the other through the existing legacy `UpdateTemplateContentUseCase.execute(...)`. Assert: the resulting `Template.metadata` dicts are byte-for-byte identical (modulo `body_params`-ordering / non-deterministic timestamp fields, if any). This pins US2's "the endpoint MUST persist the LOCAL canonical shape" guarantee by direct comparison against the legacy PATCH endpoint's output.

- [ ] T021 [P] [US2] Add a `task_create_template`-not-fired test (NEW or extend `test_validate_template_sample.py`). Patch `retail.templates.tasks.task_create_template.delay` and submit a UTILITY-classifying payload. Assert `mocked_delay.assert_not_called()`. Pins FR-006 / A10 — Direct Send templates skip the Integrations push because pushing would trigger Meta error 132021 ("A template with the same name already exists" per `docs/direct-send-api-beta-integration.md:976`) on the next Direct Send dispatch.

**Checkpoint**: US2 is fully functional. The lockstep guarantee between local writes and broadcast rendering is pinned by an integration test that breaks loudly if anyone diverges the two paths.

---

## Phase 5: User Story 3 - Sample submission failures don't corrupt local template state (Priority: P2)

**Goal**: Exhaustively cover the failure-path branches inside `ValidateTemplateSampleUseCase.execute` and the view's exception-translation block. After this phase, every error mode from FR-005c + FR-007b–e + spec.md US3 has a unit test plus a view test asserting the HTTP response shape AND zero-side-effects guarantee (no `metadata` rewrite, no new `Version`, no `current_version` advance, no audit-log noise beyond the one error event).

**Independent Test**: Per spec.md US3 — for each of four failure scenarios (Meta unavailable, Meta invalid response, WABA not configured, template not Direct Send-eligible), fire the endpoint and assert (a) the deterministic HTTP status + body shape, (b) the local template (`metadata`, `current_version`, `Version.status`) is byte-identical to its pre-call state, (c) the matching audit-log event was emitted at the correct log level.

### Implementation for User Story 3

- [ ] T022 [P] [US3] Add use-case tests for the Meta-unavailable path in `retail/templates/tests/usecases/test_validate_template_sample.py`. Two cases: (a) `MetaService.submit_template_sample` raises `CustomAPIException` → use case raises `MetaSampleUnavailableError` with `status_code` + `meta_response` preserved from the original exception; (b) `MetaService.submit_template_sample` raises an unexpected `Exception` → use case raises `MetaSampleUnavailableError` with `meta_response=None`. In both cases assert: no local mutation (use `Template.metadata`, `Template.current_version`, `Version.status` pre/post snapshots); `_emit META_ERROR` was called at **ERROR** level with `exc_info=True` per FR-008b (verify via `with self.assertLogs(..., level="ERROR")` and inspect the `LogRecord.exc_info` attribute); the use case re-raises (so the view's `except` block catches).

- [ ] T023 [P] [US3] Add use-case tests for the Meta-invalid-response path. Four cases: (a) Meta returns HTTP 200 with body `{"success": false, "error": {...}}` → `MetaInvalidResponseError` raised; (b) Meta returns HTTP 200 with body `{"success": true}` (no `category` key) → `MetaInvalidResponseError` raised; (c) Meta returns HTTP 200 with body `{"success": true, "category": ""}` (empty `category`) → `MetaInvalidResponseError` raised; (d) [C4 from speckit-analyze] Meta returns HTTP 200 with body `{"success": false, "category": "UTILITY"}` (success:false wins over category present) → `MetaInvalidResponseError` raised. In all cases assert: no local mutation; `meta_response` on the exception carries the raw Meta body verbatim; `_emit META_INVALID_RESPONSE` was called at **WARNING** level per FR-008b (`with self.assertLogs(..., level="WARNING")`) with the raw body (truncated per FR-008c safety cap).

- [ ] T024 [P] [US3] Add use-case tests for the WABA-not-configured path. Four cases per `data-model.md` §3: (a) no `ProjectOnboarding` row for the project → `WabaNotConfiguredError`; (b) `config = {}` (no `channels` key) → `WabaNotConfiguredError`; (c) `config = {"channels": {}}` (no `wpp-cloud` sub-key) → `WabaNotConfiguredError`; (d) `config["channels"]["wpp-cloud"]["channel_data"]["waba_id"] == ""` → `WabaNotConfiguredError`. Assert: no Meta call was made (`mocked_meta_service.submit_template_sample.assert_not_called()`); no local mutation; `_emit WABA_NOT_CONFIGURED` was called at **WARNING** level per FR-008b.

- [ ] T025 [P] [US3] Add use-case tests for the not-Direct-Send-eligible path. Three cases per `data-model.md` §4: (a) `template.integrated_agent is None` (custom template never assigned) → `NotDirectSendEligibleError` with `integrated_agent_uuid=null`; (b) `template.integrated_agent.config == {}` → `NotDirectSendEligibleError` with `direct_send_flag=False`; (c) `template.integrated_agent.config == {"direct_send": False}` → `NotDirectSendEligibleError` with `direct_send_flag=False`. Assert: no `ProjectOnboarding` lookup was performed (gate runs BEFORE WABA resolution per `data-model.md` §9); no Meta call; no local mutation; `_emit NOT_DIRECT_SEND_ELIGIBLE` was called at **WARNING** level per FR-008b with the IntegratedAgent identifier (or `null`) and the resolved flag.

- [ ] T026 [P] [US3] Add view tests for the error-path HTTP boundary in `retail/templates/tests/views/test_validate_template_sample_view.py`. Five cases, each patching the use case to raise the corresponding exception and asserting the response body + status per `contracts/sample-endpoint-request-response.md`: (a) `NotDirectSendEligibleError` → HTTP 400 with `{"detail": "Template is not Direct Send-eligible", "error_code": "not_direct_send_eligible"}` (no `meta_response` field); (b) `WabaNotConfiguredError` → HTTP 400 with `{"detail": "WABA not configured for this project", "error_code": "waba_not_configured"}`; (c) `MetaSampleUnavailableError(meta_response={...})` → HTTP 502 with `{"detail": "Meta sample submission failed", "error_code": "meta_unavailable", "meta_response": {...}}`; (d) `MetaSampleUnavailableError(meta_response=None)` → HTTP 502 WITHOUT the `meta_response` field; (e) `MetaInvalidResponseError` → HTTP 502 with `{"detail": "Meta did not return a category", "error_code": "meta_invalid_response", "meta_response": {...}}`.

- [ ] T027 [P] [US3] Add a use-case test for the partial-failure-after-UTILITY path. Mock Meta to return UTILITY but cause the downstream `_apply_metadata_update` (or `_create_version_with_options`) to raise an exception. Assert: the original exception propagates (not wrapped); `_emit LOCAL_UPDATE_FAILED_AFTER_META_APPROVAL` was called at **ERROR** level with `exc_info=True` per FR-008b AND with the Meta sample id (when Meta returned one); the audit-log event fires regardless of how far the partial mutation got. This pins FR-006c — operator-retry is the documented recovery path; no rollback is attempted.

- [ ] T027b [P] [US3] [C2 from speckit-analyze — SC-008 cross-tenant isolation] Add a view test in `retail/templates/tests/views/test_validate_template_sample_view.py` dedicated to SC-008. Two cases: (a) submit with `Project-Uuid` header = project A's UUID and body `project_uuid` = project B's UUID; expect HTTP 400 with `error_code = "project_uuid_mismatch"`, no use-case invocation (`MetaService.submit_template_sample.assert_not_called()`), no DB write (Template state byte-identical before/after), and a `[TemplateSampleValidation] project_uuid_mismatch: ...` WARNING-level audit log line; (b) submit with `Project-Uuid` header AND body `project_uuid` both equal to project A's UUID, but the `template_uuid` path param points at a Template whose `integrated_agent.project` is project B — expect the request to fail (either HTTP 404 via DRF default if the template lookup is project-scoped, OR a domain-level rejection that the audit log surfaces with the appropriate event name). The exact failure mode depends on whether the use case adds project-scoped Template filtering; document the chosen behavior in the test and reference SC-008. (Depends on T015, T016.)

**Checkpoint**: US3 is fully functional. Every failure path has a deterministic HTTP response shape, a zero-side-effects guarantee on local state, and an audit-log event at the correct level (per-event log-level assertions pin FR-008b in CI). The SC-008 cross-tenant isolation guarantee is pinned by T027b. The endpoint fails closed in every error mode.

---

## Phase 6: User Story 4 - Frontend gets a payload it can render without translation (Priority: P3)

**Goal**: Pin the request / response schema parity guarantees so the frontend can call the new endpoint by changing only the URL path (no field renames, no removed fields, no added required fields) AND render the response without a second `GET` round-trip.

**Independent Test**: Per spec.md US4 — diff the new endpoint's request body schema against `UpdateTemplateContentSerializer`; diff the UTILITY response's `template` field against `ReadTemplateSerializer`. Both diffs MUST be field-level subsets / equal.

### Implementation for User Story 4

- [ ] T028 [P] [US4] Add schema-parity tests in `retail/templates/tests/views/test_validate_template_sample_view.py` (or a new sibling test file `test_validate_template_sample_schema_parity.py` if separation aids readability). Two cases: (a) request schema parity — instantiate both `UpdateTemplateContentSerializer()` and `ValidateTemplateSampleSerializer()`, compare `set(serializer.fields.keys())` — assert the new serializer's field set is `UpdateTemplateContentSerializer.fields` exactly (no added, no removed, no renamed fields); the `validate_*` overrides are the only difference (FR-014); (b) response schema parity — submit a UTILITY-mocked request, parse the response, instantiate `ReadTemplateSerializer(template).data` independently on the post-call template instance, assert `response.data["template"] == ReadTemplateSerializer(template).data` (byte-for-byte). The wrapper has exactly four top-level keys `{category, template_updated, template, meta_sample_response}` (the auto-generated DRF "fields are extra" assertion catches any future drift).

**Checkpoint**: US4 is fully functional. The frontend contract is structurally pinned by tests that break loudly if anyone renames a field or drops `meta_sample_response` from the wrapper.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates, observability sanity checks, and PR-prep work.

- [ ] T029 [P] Run the end-to-end quickstart per `quickstart.md` steps 3, 5, 6, 7, 8, 9 against a staging-like environment. Capture the audit-log lines for each scenario and confirm the `[TemplateSampleValidation] <event_name>: k=v` shape per FR-008 / FR-008a (this is the post-deploy operator-observability sanity check that no unit test exercises — it pins the actual rendered log shape that dashboards will filter on).

- [ ] T030 [P] Run `poetry run coverage run manage.py test && poetry run coverage report -m | tail -40 && poetry run python contrib/compare_coverage.py` from the repo root. Verify (a) no coverage regression on changed files (Constitution Principle III), (b) `compare_coverage.py` reports `Number of test lines increased` (or at minimum not decreased), (c) every new file under `retail/templates/usecases/`, `retail/templates/adapters/`, `retail/templates/strategies/` and the strategy-refactor diff shows full branch coverage on the new code. Capture the coverage diff for the PR description.

- [ ] T031 [P] Run `pre-commit run --all-files` from the repo root. Verify all hooks (Black, flake8, configured via `.pre-commit-config.yaml`) pass clean. If any auto-fix is applied, commit it separately with `chore: pre-commit auto-fixes`.

- [ ] T031b [P] [C12 from speckit-analyze — FR-010 verification] Run `poetry run python manage.py makemigrations --check --dry-run` from the repo root. The exit code MUST be 0 (no migration would be generated). This is the structural gate for FR-010's "zero schema changes" guarantee. Any non-zero exit indicates an accidental model change and the PR is blocked until either the change is reverted or the spec is amended to allow the migration. Capture the (empty) output for the PR description.

- [ ] T032 Manually grep the audit-log output during a local test run for `[TemplateSampleValidation]` and confirm NO verbatim `template_body` / `template_header` / `template_footer` / button text appears in the rendered log lines (FR-008c PII redaction). Customer-facing content MUST appear only as length / presence flags. Identifiers (UUIDs, IDs) MAY appear verbatim. Example grep: `poetry run python manage.py test retail.templates.tests.usecases.test_validate_template_sample 2>&1 | grep TemplateSampleValidation | grep -E "template_body=[\"']|template_header=[\"']"` should return ZERO matches.

- [ ] T033 Prepare the PR description per Constitution Principle V — title `feat: add Direct Send template sample validation endpoint` (58 chars, well under 72-char ceiling); body uses the `## What` / `## Why` template; reference `spec.md`, `plan.md`, and the relevant FR / SC tokens for traceability; call out the two documented deviations from Complexity Tracking (Service-layer "propagate instead of swallow" for `MetaService.submit_template_sample`, and the spec-kit branch-name convention). Cross-link the related specs: 002 (Direct Send broadcasts), 003 (template category webhook).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; T001 can run immediately.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS all user-story phases. Within Phase 2, the parallel groups are: {T002, T003, T004, T008, T010, T012, T014} can run fully in parallel (different files, no inter-dependencies); T005 → T006 → T007 are sequential within the Meta-side chain; T009 depends on T008; T011 depends on T010; T013 depends on T012.
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2). T015 → T016 are sequential (view depends on use case); T017 and T018 can run in parallel against each other and against T015 / T016 if developed concurrently.
- **User Story 2 (Phase 4)**: Depends on US1 (Phase 3 — T015, T016 must be done; the integration tests load and exercise the use case). T019 / T020 / T021 can run in parallel.
- **User Story 3 (Phase 5)**: Depends on US1 (Phase 3 — same reason; the failure-path tests load the use case). T022 / T023 / T024 / T025 / T026 / T027 / T027b can run in parallel.
- **User Story 4 (Phase 6)**: Depends on US1 (Phase 3) + on the serializer (T012). T028 is a single task.
- **Polish (Phase 7)**: Depends on the user-story phases the team chooses to deliver in this PR (US1 minimum for the MVP slice, all four for the full feature).

### User Story Dependencies

- **US1 (P1)**: Foundational only — no inter-story dependencies.
- **US2 (P1)**: US1 only (US2's tests load and exercise US1's use case + broadcast renderer).
- **US3 (P2)**: US1 only.
- **US4 (P3)**: US1 only (US4's tests load the response of US1's view).

US2 / US3 / US4 are INDEPENDENT of each other — they can be implemented in any order or in parallel after US1 is done.

### Within Each User Story

- US1: T015 (use case) → T016 (view) → T017 (use-case tests) + T018 (view tests) — tests can run in parallel after the implementation lands.
- US2 / US3 / US4: each task within the story is independent of the others (each is a self-contained test file or a sibling test method) — can all run in parallel.

### Parallel Opportunities

- All [P]-marked Foundational tasks (T002, T003, T004, T008, T010, T012, T014) can run in parallel — 7-way parallelism in Phase 2.
- All [P]-marked tests within a single user story can run in parallel — e.g. T017 + T018 in US1, T019 + T020 + T021 in US2, T022-T027 in US3.
- Across user stories (after US1 lands): US2, US3, US4 can be developed in parallel by different team members. Each story's tests run independently.

---

## Parallel Example: Foundational Phase

```bash
# Launch all leaf scaffolding in parallel (different files, no shared mutable state):
Task: "T002 — Add four domain exceptions to retail/templates/exceptions.py"
Task: "T003 — Extend MetaClientInterface at retail/interfaces/clients/meta/client.py"
Task: "T004 — Extend MetaServiceInterface at retail/interfaces/services/meta.py"
Task: "T008 — Refactor UpdateNormalTemplateStrategy to extract two helpers"
Task: "T010 — Create direct_send_sample_translator.py pure-function module"
Task: "T012 — Add ValidateTemplateSampleSerializer to retail/templates/serializers.py"
Task: "T014 — Define DTOs and Enums in retail/templates/usecases/validate_template_sample.py"
```

## Parallel Example: User Story 3 Tests

```bash
# All US3 failure-path tests touch the same test file but test independent
# methods, so they can be developed in parallel and merged in any order:
Task: "T022 — Use-case tests for Meta-unavailable path"
Task: "T023 — Use-case tests for Meta-invalid-response path"
Task: "T024 — Use-case tests for WABA-not-configured path"
Task: "T025 — Use-case tests for not-Direct-Send-eligible path"
Task: "T026 — View tests for error-path HTTP boundary"
Task: "T027 — Use-case test for partial-failure-after-UTILITY path"
Task: "T027b — View test for SC-008 cross-tenant isolation"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001 — branch + test-suite verification).
2. Complete Phase 2: Foundational (T002–T014 — the building blocks). CRITICAL — blocks every user-story phase.
3. Complete Phase 3: User Story 1 (T015–T018 — the happy-path orchestration + view + tests).
4. **STOP and VALIDATE**: Run the quickstart steps 3 and 5 manually. Confirm the endpoint accepts a UTILITY-classifying body edit and a MARKETING-classifying body edit and produces the expected HTTP 200 responses with correct local state. This is the MVP slice — operators can use the endpoint for the dominant case.
5. Deploy / demo if the MVP is sufficient for the immediate operator need.

### Incremental Delivery

1. Setup + Foundational → Foundation ready (no observable endpoint behavior).
2. Add US1 → MVP — operators have the happy path. Test independently per Phase 3 checkpoint.
3. Add US2 → lockstep guarantee proven by integration test. No new HTTP surface; deepens confidence.
4. Add US3 → failure-path coverage. Operators see deterministic errors for Meta outages / WABA misconfiguration / non-eligible templates.
5. Add US4 → schema-parity tests. Frontend integration is regression-proof.
6. Polish → coverage report + lint + log redaction sanity + PR prep.

### Parallel Team Strategy

With multiple developers after Foundational completes:

1. Developer A: US1 implementation (T015 → T016).
2. Developer B: US1 + US2 tests (T017, T018, T019, T020, T021).
3. Developer C: US3 tests (T022 → T027b).
4. Developer D: US4 test (T028) + Polish (T029 → T033 + T031b).

Developers B / C / D can begin their test development as soon as Developer A finishes T015 (the use case execute body); T016 (the view) only blocks the view-level tests (T018, T026, T028).

---

## Notes

- [P] tasks = different files OR independent test methods, no incomplete dependencies.
- [Story] label maps task to its user story for traceability against `spec.md`.
- Each user story is independently completable — US1 is the MVP slice and can ship alone if needed.
- Verify tests fail before implementing (TDD-friendly — each test task can be written ahead of its implementation, except T015 / T016 which are implementation-first by nature).
- Commit after each logical group (e.g. one commit per task, or one per US-phase if tasks are small).
- Stop at any checkpoint to validate the increment independently.
- Avoid: vague task wording, same-file conflicts within a single [P] group, cross-story dependencies that would break the independent-testability guarantee.
- The Constitution's Principle III (Test Coverage Parity, NON-NEGOTIABLE) means EVERY new branch must have a corresponding test in the same PR. The task list above enumerates the tests explicitly — running `contrib/compare_coverage.py` at T030 is the structural gate that catches any missing test.
