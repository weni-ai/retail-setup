---

description: "Task list for the Direct Send Template Incorrect-Category Webhook feature"
---

# Tasks: Direct Send Template Incorrect-Category Webhook

**Input**: Design documents from `/specs/003-template-category-webhook/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/direct-send-category-webhook.md`, `quickstart.md`

**Tests**: Tests are REQUIRED for this feature. The spec mandates test coverage per Constitution Principle III (`/home/paulobernardoaf/.cursor/rules/test-coverage-and-external-dependencies.mdc`) — every new branch added by this PR is exercised by a unit or integration test in the same PR.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested independently (delivered incrementally as an MVP slice).

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`); omitted for Setup / Foundational / Polish phases
- File paths in descriptions are absolute against the repo root (`retail/...`)

## Path Conventions

- Web service (Django + DRF) — all source paths relative to the repo root
- New production code lands under `retail/webhooks/templates/` (see `plan.md` §Project Structure)
- New tests land under `retail/webhooks/templates/tests/` (folder created by this PR — the legacy webhook has no tests; backfilling is out of scope per `plan.md` Complexity Tracking row 1)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the empty `tests/` package skeleton so the unit-test discovery (Django's `manage.py test`) finds the new test modules added by later phases. The existing webhook has no `tests/` folder at all (Complexity Tracking row 1 in `plan.md`), so the package init files are net-new.

- [ ] T001 [P] Create empty `__init__.py` at `retail/webhooks/templates/tests/__init__.py`
- [ ] T002 [P] Create empty `__init__.py` at `retail/webhooks/templates/tests/usecases/__init__.py`
- [ ] T003 [P] Create empty `__init__.py` at `retail/webhooks/templates/tests/views/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Lay down the shared types (`DTO`, `Result`, `FlaggingReason`, `EventName`), the audit-log helper that enforces the `[DirectSendCategoryWebhook] event_name: k=v` shape (FR-009 / FR-009a–e), the use case skeleton with the `received` / `completed` / `unexpected_error` envelope (FR-009c, FR-010b), the inbound serializer (FR-003), the thin view (FR-001, FR-002), and the URL mount. Every user story depends on this skeleton being in place before per-story branches can be implemented.

**CRITICAL**: No user-story work can begin until Phase 2 is complete.

- [ ] T004 Create `DirectSendCategoryDTO` (`@dataclass(frozen=True)` with `project_uuid: UUID`, `app_uuid: UUID`, `template_name: str`, `template_category: str`, `template_correct_category: str`) in new file `retail/webhooks/templates/usecases/direct_send_category.py` (Decision 9, data-model §5.1)
- [ ] T005 Add `DirectSendCategoryResult` (`@dataclass(frozen=True)` with `templates_updated: int`, `integrated_agents_inspected: int`, `detail: str`, plus a `to_dict()` method whose keys are exactly `detail` / `templates_updated` / `integrated_agents_inspected`) to `retail/webhooks/templates/usecases/direct_send_category.py` (Decision 10, data-model §5.2, contract §2.1)
- [ ] T006 Add `FlaggingReason(str, Enum)` (`CATEGORY_MISMATCH`, `CATEGORY_NOT_UTILITY`, `CATEGORY_MISMATCH_AND_NOT_UTILITY`) and `EventName(str, Enum)` (the 10 closed tokens enumerated by FR-009a) to `retail/webhooks/templates/usecases/direct_send_category.py` (data-model §5.3, §5.4)
- [ ] T007 Add the audit-log helper to `retail/webhooks/templates/usecases/direct_send_category.py` — a single private `_emit(event: EventName, level: int, **kv)` method that formats every line as `[DirectSendCategoryWebhook] {event.value}: k1=v1 k2=v2 ...` and routes to `logger.{info,warning,error}` per the level argument; plus the three envelope helpers that fire on every well-formed request: `_emit_received` (INFO), `_emit_completed` (INFO), and `_emit_unexpected_error` (ERROR with `exc_info=True`). The seven per-IA outcome emit helpers are added by the user-story tasks that wire them — `_emit_flagged` by T014 (US1), `_emit_no_action_required` by T015 (US1), `_emit_flag_replay_noop` and `_emit_no_action_required_already_flagged` by T020 (US2), and `_emit_no_matching_integrated_agent` / `_emit_template_not_found` / `_emit_template_has_no_current_version` by T023 / T024 (US3). Per FR-009b, the per-IA helpers added later MUST route at INFO for `flagged` / `flag_replay_noop` / `no_action_required` / `no_action_required_already_flagged`, and at WARNING for `no_matching_integrated_agent` / `template_not_found` / `template_has_no_current_version`. The `_emit` method is the **only** place in the codebase that knows the log-line shape (Constitution Principle IV / plan.md §Constitution Check IV)
- [ ] T008 Add `DirectSendCategoryWebhookUseCase` class to `retail/webhooks/templates/usecases/direct_send_category.py` with: (a) an `execute(dto: DirectSendCategoryDTO) -> DirectSendCategoryResult` method that emits `received` at start, calls the fully-implemented `_lookup_integrated_agents` from sub-clause (c), iterates over the resulting queryset with a fan-out loop body that is initially a `pass` placeholder (filled in by US1's T015), and emits `completed` at success-path exit; (b) an outer `try / except Exception as exc` block around the body that emits `unexpected_error` with `exc_info=True` and re-raises (so the view's 500 path is driven by the re-raise — FR-009b, FR-010b); (c) a `_lookup_integrated_agents(dto)` private method that returns `IntegratedAgent.objects.filter(project__uuid=dto.project_uuid, templates__versions__integrations_app_uuid=dto.app_uuid).distinct()` (Decision 2, data-model §2)
- [ ] T009 [P] Add `DirectSendCategoryWebhookSerializer` (DRF `Serializer` subclass — NOT `ModelSerializer` — with `project_uuid = UUIDField(required=True)`, `app_uuid = UUIDField(required=True)`, `template_name = CharField(required=True, allow_blank=False)`, `template_category = CharField(required=True, allow_blank=False)`, `template_correct_category = CharField(required=True, allow_blank=False)`) to existing file `retail/webhooks/templates/serializers.py` (FR-003 / FR-003a — no allow-list on category values; contract §1.2). Do NOT declare a `Meta` class, do NOT add a `validate(self, attrs)` method that inspects or rejects unknown keys, and do NOT add per-field `choices=` constraints. The default DRF `Serializer` silently ignores unknown JSON keys — this is the forward-compatibility surface contract §1.3 / FR-003 last sentence mandate (if Integrations adds a new field like `detected_at` in a future release, Retail accepts the payload without a coordinated deploy). A `validate(attrs)` that rejects unknown keys would break the contract
- [ ] T010 [P] Create `DirectSendCategoryWebhook` APIView in new file `retail/webhooks/templates/views/direct_send_category.py` — extends `rest_framework.views.APIView`, declares `permission_classes = [CanCommunicateInternally]` at class level, exposes a `post(self, request)` method that (1) instantiates `DirectSendCategoryWebhookSerializer(data=request.data)` and calls `serializer.is_valid(raise_exception=True)` — this call MUST stay OUTSIDE the try/except in step (5) so DRF's standard `ValidationError → HTTP 400` translation (FR-010a) is preserved, (2) builds a `DirectSendCategoryDTO(**serializer.validated_data)`, (3) instantiates the use case and calls `result = use_case.execute(dto)` — this single call is the ONLY statement wrapped by step (5)'s try/except, (4) returns `Response(result.to_dict(), status=HTTP_200_OK)`, (5) wraps **only** the `use_case.execute(dto)` call from step (3) in a `try / except Exception` that returns `Response({"detail": "Internal server error"}, status=HTTP_500_INTERNAL_SERVER_ERROR)` — wrapping the entire post body (e.g. including step 1's `is_valid(raise_exception=True)`) would silently convert validation errors into HTTP 500, breaking FR-010a (FR-001, FR-002, FR-010, FR-010b; Constitution Principle I — view is thin, no ORM, no business logic, no auth check in the body)
- [ ] T011 Add URL entry `path("templates-status/api/category-notification/", DirectSendCategoryWebhook.as_view(), name="direct-send-category-webhook")` to `retail/webhooks/templates/urls.py` — preserve the existing `TemplatesStatusWebhook` entry verbatim (Decision 1, plan.md §Constraints "existing webhook untouched"). Import `DirectSendCategoryWebhook` from `retail.webhooks.templates.views.direct_send_category`

**Checkpoint**: skeleton compiles, URL is mounted, POSTing a valid payload returns HTTP 200 with `templates_updated=0` and `integrated_agents_inspected=0` (the fan-out loop body is still a placeholder). All three user stories can now be implemented in parallel.

---

## Phase 3: User Story 1 - Block dispatch when Integrations detects an incorrect template category (Priority: P1) — MVP

**Goal**: When the webhook fires with a payload whose category fails the FR-006 two-clause check, every matched IntegratedAgent's Template has its `current_version.status` written to `"FLAGGED"`, the HTTP 200 response reports the counters, the audit log emits one `flagged` line per Version transitioned with the right `reason=` token, and the next broadcast attempt for the flagged template is skipped by spec 002's pre-existing dispatch gate.

**Independent Test**: With (a) a project that has at least one IntegratedAgent whose templates were created against a specific `app_uuid`, and (b) one of those templates having a current version in `APPROVED`, fire the webhook with `(project_uuid, app_uuid, template_name)` and `template_category="MARKETING"`. Verify (1) the Version's `status` is `FLAGGED`, (2) HTTP 200 response body reads `{"detail": "Templates flagged.", "templates_updated": 1, "integrated_agents_inspected": 1}`, (3) the audit log emits the three lines `received` / `flagged` (with `reason=category_not_utility`) / `completed`, and (4) a subsequent order-status webhook for the same template is skipped by `Broadcast.get_current_template`.

### Implementation for User Story 1

- [ ] T012 [US1] Add `_lookup_template(integrated_agent, template_name)` private method to `retail/webhooks/templates/usecases/direct_send_category.py` returning `integrated_agent.templates.select_related("current_version").filter(name=template_name).first()` (Decision 4, FR-005 — case-sensitive exact match, eager-load `current_version` for the flagging-condition read)
- [ ] T013 [US1] Add `_evaluate_flagging_condition(dto) -> bool` (returns `dto.template_category != dto.template_correct_category or dto.template_category != "UTILITY"`) and `_determine_flagging_reason(dto) -> FlaggingReason` (covers the four cells of the FR-006 / FR-006b truth table — composite reason when both clauses fire) to `retail/webhooks/templates/usecases/direct_send_category.py` (FR-006, FR-006a, FR-006b, data-model §5.3)
- [ ] T014 [US1] Add `_flag_version(version, template, integrated_agent, dto, reason)` private method to `retail/webhooks/templates/usecases/direct_send_category.py` — captures `previous_status = version.status`, sets `version.status = "FLAGGED"`, calls `version.save(update_fields=["status"])` (FR-007b — `update_fields` is mandatory), and emits the `flagged` audit line via the helper from T007 carrying the full FR-009d `k=v` payload (`project_uuid`, `app_uuid`, `template_name`, `template_category`, `template_correct_category`, `integrated_agent_uuid`, `template_uuid`, `version_uuid`, `previous_status`, `new_status=FLAGGED`, `reason={reason.value}`). The early-return guard for `previous_status == "FLAGGED"` is added by US2 (T020) — for now this method always writes
- [ ] T015 [US1] Replace the fan-out `pass` placeholder in `execute()` with the per-IA loop in `retail/webhooks/templates/usecases/direct_send_category.py`: for each `integrated_agent` returned by `_lookup_integrated_agents(dto)`, increment a local `inspected` counter, look up the template via `_lookup_template`, and when both the template and its `current_version` are non-None, branch on `_evaluate_flagging_condition(dto)` — if true, dispatch to `_flag_version` and increment a local `flagged` counter; if false, emit `no_action_required` via a new private `_emit_no_action_required(integrated_agent, template, version, dto)` method that wraps `self._emit(EventName.NO_ACTION_REQUIRED, INFO, **kv)` (FR-006 no-fire / FR-009a / FR-009b / FR-009d — carries `project_uuid`, `app_uuid`, `template_name`, `template_category`, `template_correct_category`, `integrated_agent_uuid`, `template_uuid`, `version_uuid`, `previous_status`). When `template is None` OR `template.current_version is None`, the loop MUST add an `"mvp_silent_skip"` placeholder outcome tag (consumed by T016's mapping) and `continue` without emitting an audit line and without incrementing the `flagged` counter — this is the deterministic placeholder behavior for the MVP slice (US1 only); US3 (T024) replaces both the silent `continue` AND the placeholder outcome tag with the explicit `template_not_found` / `template_has_no_current_version` emissions plus their own outcome tags. The deterministic skip prevents the MVP slice from raising `AttributeError` on `None.status` or returning a partially-defined `detail` string
- [ ] T016 [US1] Compute and pass the `detail` string into `DirectSendCategoryResult` at the end of `execute()` in `retail/webhooks/templates/usecases/direct_send_category.py` using the closed enumeration from data-model §5.2 / contract §2.3: track per-IA outcome tags during the fan-out, then map the set of observed outcomes to `"Templates flagged."` / `"Already flagged."` / `"No action required."` / `"No matching IntegratedAgent."` / `"Template not found."` / `"Mixed outcomes."`. The `"mvp_silent_skip"` placeholder outcome tag added by T015 (MVP-only — fires when `template is None` OR `current_version is None`) MUST map to `"No action required."` so a misrouted-template call during the MVP slice returns a deterministic `detail` instead of falling through to an undefined branch; T024 replaces every `"mvp_silent_skip"` outcome tag with the explicit `"template_not_found"` / `"template_has_no_current_version"` outcome tags and the mapping shifts those to `"Template not found."` accordingly. (The `"Already flagged."`, `"No matching IntegratedAgent."`, and `"Template not found."` branches do not fire under US1 alone — they require US2/US3 use case logic — but the mapping logic is added in full now so US2/US3 only have to wire the new outcome tags)

### Tests for User Story 1

- [ ] T017 [P] [US1] Add unit tests for `DirectSendCategoryWebhookUseCase` to new file `retail/webhooks/templates/tests/usecases/test_direct_send_category.py` covering: (a) single-IA flagging for each `FlaggingReason` variant — `category_mismatch` (`UTILITY` vs `MARKETING`), `category_not_utility` (`MARKETING` vs `MARKETING`), `category_mismatch_and_not_utility` (`MARKETING` vs `AUTHENTICATION`) — parametrized over `previous_status ∈ {"APPROVED", "PAUSED", "PENDING", "REJECTED", "DELETED"}` (spec.md Edge Case row 6 — `FLAGGED` dominates over `PENDING` / `REJECTED` because the user-facing risk outweighs the existing non-`APPROVED` reason; the remaining `Version.STATUS_CHOICES` values not in this parametrization — `IN_APPEAL`, `PENDING_DELETION`, `DISABLED`, `LOCKED` — are equivalence-class members that converge to identical FLAGGED behavior because the early-return guard in T020 only short-circuits on `previous_status == "FLAGGED"`, so testing them adds no new branch coverage), asserting in every cell the Version's `status` is `"FLAGGED"` after the call, `Version.save` was called with `update_fields=["status"]`, the Template's `current_version_id` is unchanged after the call (FR-007a — only `Version.status` mutates; the FK pointer is preserved across the flagging write), and the `flagged` audit line carries the right `reason=` token and `previous_status=<starting value>`; (b) `UTILITY`/`UTILITY` payload → no-action path, no `Version.save` call, audit line is `no_action_required`; (c) multi-IA fan-out (US1 scenario 4) — two IAs with same `app_uuid` both get their Version flagged, `templates_updated=2`, `integrated_agents_inspected=2`; (d) cross-tenant exclusion (SC-006) — IA in project B with same `app_uuid` is excluded by the queryset, audit log makes no reference to it; (e) counter parity — the `templates_updated` and `integrated_agents_inspected` returned in the result equal the values emitted on the `completed` audit line; (f) `received` line is emitted exactly once at start with the full payload, `completed` line exactly once at end with the counters (FR-009c sequence); (g) FR-009e payload-key assertion — for each emitted log record across the happy path, assert `set(record.args.keys())` equals exactly the FR-009d-pinned keys for that event name (no extra keys leak from `validated_data`, no stray Retail-internal identifiers escape); (h) blocked-project still processes (spec.md Edge Cases row 12 — `Project.is_blocked=True` does NOT gate this webhook because blocking gates outbound flows, not inbound state-correctness signals): build a fixture with `Project.is_blocked=True`, fire a flagging payload, assert (h.1) the Version's `status` is `"FLAGGED"` after the call, (h.2) the `flagged` audit line is emitted with the same `k=v` payload as the unblocked case, and (h.3) `templates_updated=1`; (i) FR-009e no-truncation / no-redaction — fire a flagging payload with a 200-character `template_correct_category` value (e.g. `"X" * 200`) and assert the `flagged` audit line records the value verbatim with no truncation, no hashing, no ellipsis (the payload key set equals the FR-009d enumeration and the value byte-string is identical to the input). Use `unittest.mock.patch` on `Version.save` to assert the call args; use Django's `TestCase` with `setUp` that builds the IA/Template/Version fixtures; use `self.assertLogs(level="INFO")` to capture log records for sub-tests (g) and (i)
- [ ] T018 [P] [US1] Add view-level HTTP tests for `DirectSendCategoryWebhook` to new file `retail/webhooks/templates/tests/views/test_direct_send_category.py` covering: (a) HTTP 200 happy path — POST a valid payload, assert response body is exactly `{"detail": "Templates flagged.", "templates_updated": 1, "integrated_agents_inspected": 1}` and the underlying Version is now `FLAGGED`; (b) HTTP 401 — POST with no `Authorization` header; (c) HTTP 403 — POST with a user lacking `can_communicate_internally` permission; (d) HTTP 400 — three sub-cases: missing required field (drop `template_correct_category`), malformed UUID (`project_uuid="not-a-uuid"`), blank string (`template_name=""`); (e) HTTP 500 — patch `DirectSendCategoryWebhookUseCase._lookup_integrated_agents` (a method invoked **inside** `execute()`, NOT `execute()` itself) to raise `Exception("db lost")` so the use case's outer `try / except Exception as exc` block from T008 runs and emits the audit line; assert (i) response body is `{"detail": "Internal server error"}`, (ii) an `unexpected_error` audit line was emitted with `exc_info=True` (FR-009b), (iii) a `received` line was emitted before the exception fired (FR-009c — the received line is emitted at request start, before the lookup), and (iv) NO `completed` line was emitted (FR-009c last paragraph). Patching `execute` itself would bypass the in-method try/except introduced by T008, so the audit line would never fire and assertions (ii) / (iii) would fail; always patch a method invoked from inside `execute` instead. Use `BaseTestMixin.setup_internal_user_permissions` (`retail/internal/test_mixins.py:130`) for auth setup, mirroring the existing internal-webhook view tests pattern
- [ ] T019 [US1] Add integration test class `DirectSendCategoryWebhookDispatchIntegrationTest(TestCase)` to `retail/webhooks/templates/tests/views/test_direct_send_category.py` that exercises the cross-spec contract pinned by FR-013 / SC-002: (1) seed a project + IA + Template + `APPROVED` Version, (2) POST the webhook with a flagging payload, (3) re-fetch the Version and assert `status == "FLAGGED"`, (4) instantiate `retail.agents.domains.agent_webhook.services.broadcast.Broadcast` and call its `get_current_template(integrated_agent, lambda_data)` method with `lambda_data` shaped like a real order-status event whose `template` field matches the flagged template's name, (5) assert the return value is `None` (the dispatch gate skipped the flagged template). This pins the integration with spec 002's dispatch path without modifying it

**Checkpoint**: User Story 1 fully functional and independently unit-testable. The MVP slice is a **development checkpoint, NOT a shipping cut-line**: until US3 (T023/T024) lands, the silent-skip behavior on misrouted payloads violates FR-004b, FR-005, and FR-005a (each MUSTs an audit-log entry that the MVP slice does not emit). The happy path works, the dispatch gate honors `FLAGGED`, and the audit log emits the right shape on the success path; replays will (a) pollute the audit log with duplicate `flagged` lines AND (b) issue redundant `Version.save(update_fields=["status"])` writes on every retry until US2 (T020) lands the early-return guard; misrouted payloads silently `continue` per T015's deterministic skip — the MVP-only `"mvp_silent_skip"` outcome tag added by T015 maps to `detail="No action required."` per T016 so the response shape stays deterministic (`templates_updated=0`, `integrated_agents_inspected=N`, `detail="No action required."`), but operators have no audit-log signal until US3 (T023/T024) lights up the WARNING-level `template_not_found` / `template_has_no_current_version` / `no_matching_integrated_agent` branches. The shipping cut-line is after Phase 5 (US3); see Implementation Strategy below.

---

## Phase 4: User Story 2 - Webhook is safe to retry and replay (Priority: P2)

**Goal**: When the webhook is fired more than once for the same `(project_uuid, app_uuid, template_name)` tuple, the Version's `status` converges on `FLAGGED` without a redundant `UPDATE`, the audit log distinguishes the first call's `flagged` line from subsequent calls' `flag_replay_noop` / `no_action_required_already_flagged` lines, and `templates_updated` reports 0 on every replay.

**Independent Test**: With the same setup as US1, fire the webhook twice with the same flagging payload. Verify (1) both responses are HTTP 200, (2) the first response's `templates_updated=1` and the second's `templates_updated=0`, (3) the audit log shows one `flagged` line (first call) and one `flag_replay_noop` line (second call) — both at INFO level, (4) `Version.save` was called exactly once across both requests.

### Implementation for User Story 2

- [ ] T020 [US2] Add the idempotency early-return guard to the flag-dispatch logic in `retail/webhooks/templates/usecases/direct_send_category.py` by inserting a `version.status == "FLAGGED"` check at BOTH branches of the fan-out body introduced by US1 (T015) — there are TWO insertion sites and both must be wrapped: (1) the **flagging-condition-true** branch: replace the direct `_flag_version(version, template, integrated_agent, dto, reason)` call with `if version.status == "FLAGGED": self._handle_already_flagged(version, template, integrated_agent, dto, condition_fires=True); continue` followed by the existing `_flag_version` call; (2) the **flagging-condition-false** branch: replace the direct `_emit_no_action_required(...)` call with `if version.status == "FLAGGED": self._handle_already_flagged(version, template, integrated_agent, dto, condition_fires=False); continue` followed by the existing `_emit_no_action_required` call. The new private `_handle_already_flagged(version, template, integrated_agent, dto, condition_fires: bool)` method emits either `flag_replay_noop` (when `condition_fires=True` — FR-007c / FR-008) or `no_action_required_already_flagged` (when `condition_fires=False` — US2 scenario 2 / FR-014 "never demoted") and skips the `UPDATE`; the local `flagged` counter is NOT incremented on either branch. Update the outcome-tag tracking introduced by T016 so the `"Already flagged."` `detail` string fires when every inspected IA produced one of the two `_already_flagged` tags. The `flag_replay_noop` line carries the FR-009d payload (all five payload values + IA/Template/Version uuids + `previous_status=FLAGGED`, no `new_status` and no `reason` field); the `no_action_required_already_flagged` line carries the same shape (FR-009d — neither variant carries `new_status` or `reason`). (Decision 5 — no dedup cache; FR-008a — no distributed lock)

### Tests for User Story 2

- [ ] T021 [US2] Add unit tests for the idempotency branches to `retail/webhooks/templates/tests/usecases/test_direct_send_category.py` covering: (a) Version is already `FLAGGED` + flagging payload → audit line is `flag_replay_noop`, `Version.save` is NOT called, `templates_updated=0`, `detail="Already flagged."`; (b) Version is already `FLAGGED` + non-flagging payload (`UTILITY`/`UTILITY`) → audit line is `no_action_required_already_flagged`, `Version.save` is NOT called, `templates_updated=0`, `detail="Already flagged."`; (c) call `execute` twice in the same test with the same flagging payload (no in-between mutation) → first call emits `flagged` and writes, second call emits `flag_replay_noop` and does NOT write — assert `Version.save.call_count == 1` across both calls; (d) replay with a CHANGED `template_correct_category` (spec.md Edge Case row 7 — "Template's `current_version.status` is already `FLAGGED` when a NEW flagging condition fires"): fire the webhook first with `(template_category="MARKETING", template_correct_category="MARKETING")` (reason `category_not_utility`); then fire it again with `(template_category="MARKETING", template_correct_category="AUTHENTICATION")` (would-be reason `category_mismatch_and_not_utility`) — assert (i) the second call's audit line is `flag_replay_noop` (NOT a second `flagged`), (ii) `previous_status=FLAGGED` is on the second line, (iii) the second line's `template_correct_category=AUTHENTICATION` value matches the new payload (operator-facing trail differentiation per FR-009d), (iv) `Version.save.call_count == 1` across both calls. Use `unittest.mock.patch.object(Version, "save")` to count writes
- [ ] T022 [US2] Add a view-level replay test to `retail/webhooks/templates/tests/views/test_direct_send_category.py` — POST the same payload twice via Django's test client, assert the first response body has `templates_updated=1` / `detail="Templates flagged."` and the second has `templates_updated=0` / `detail="Already flagged."`, both at HTTP 200, and the Version's `status` is `"FLAGGED"` exactly once (no demote, no re-write — pins FR-014 + SC-004)

**Checkpoint**: User Stories 1 AND 2 work independently. Replays now converge cleanly on the existing state with clean audit-log differentiation.

---

## Phase 5: User Story 3 - Misrouted or stale webhooks fail closed without partial writes (Priority: P3)

**Goal**: When the webhook payload references a project / app / template that Retail cannot locate, the response is HTTP 200, no Version row is mutated, and the audit log records the miss with the appropriate WARNING-level event (`no_matching_integrated_agent`, `template_not_found`, or `template_has_no_current_version`).

**Independent Test**: Fire the webhook three times — once with a `(project_uuid, app_uuid)` pair that matches no IntegratedAgent, once with a matching `(project_uuid, app_uuid)` but a `template_name` that no Template owns, and once with a matched Template whose `current_version` is `NULL`. Verify all three responses are HTTP 200, no Version's `status` changes, and the audit log emits one WARNING-level line per case with the right `event_name` token.

### Implementation for User Story 3

- [ ] T023 [US3] Add the `no_matching_integrated_agent` branch to `execute()` in `retail/webhooks/templates/usecases/direct_send_category.py`: when the queryset returned by `_lookup_integrated_agents(dto)` is empty (`integrated_agents.exists()` returns `False`, or equivalently `not integrated_agents`), short-circuit the fan-out, emit one `no_matching_integrated_agent` audit line at WARNING with only the five payload values (FR-009d — no IA/Template/Version identifiers because none were resolved), emit `completed` with `templates_updated=0` / `integrated_agents_inspected=0`, and return `DirectSendCategoryResult(templates_updated=0, integrated_agents_inspected=0, detail="No matching IntegratedAgent.")` (FR-004b)
- [ ] T024 [US3] Add the `template_not_found` and `template_has_no_current_version` branches inside the fan-out loop in `retail/webhooks/templates/usecases/direct_send_category.py`: when `_lookup_template(integrated_agent, dto.template_name)` returns `None`, emit `template_not_found` at WARNING with `project_uuid` / `app_uuid` / `template_name` / `integrated_agent_uuid` (FR-005, FR-009d) and `continue` to the next IA (counter `inspected` is still incremented but `flagged` is not); when the template is found but its `current_version` is `None`, emit `template_has_no_current_version` at WARNING with `project_uuid` / `app_uuid` / `template_name` / `integrated_agent_uuid` / `template_uuid` (FR-005a, FR-009d) and `continue`. Extend the outcome-tag tracking from T016 so `"Template not found."` fires when every inspected IA produced either tag, and `"Mixed outcomes."` fires when the per-IA outcomes are not all the same

### Tests for User Story 3

- [ ] T025 [US3] Add unit tests for the fail-closed branches to `retail/webhooks/templates/tests/usecases/test_direct_send_category.py` covering: (a) project exists but no IA has a Version with the requested `app_uuid` → audit line is `no_matching_integrated_agent` at WARNING with only the five payload values (assert no `integrated_agent_uuid` / `template_uuid` / `version_uuid` keys are present in the emitted `k=v` payload), result is `(0, 0, "No matching IntegratedAgent.")`; (b) project exists and IA matches but no Template named `template_name` → audit line is `template_not_found` at WARNING, no `Version.save` call, result is `(0, 1, "Template not found.")`; (c) project exists and IA matches and Template matches but `template.current_version is None` → audit line is `template_has_no_current_version` at WARNING, no `Version.save` call, result is `(0, 1, "Template not found.")` (the response `detail` collapses per data-model §5.2 footnote *); (d) multi-IA fan-out with mixed outcomes (IA-1 flags, IA-2 has no Template) → two audit lines (`flagged` for IA-1, `template_not_found` for IA-2), result is `(1, 2, "Mixed outcomes.")` per contract §6.6. Assert WARNING level via the `assertLogs(level="WARNING")` context manager
- [ ] T026 [US3] Add view-level fail-closed tests to `retail/webhooks/templates/tests/views/test_direct_send_category.py` covering the three negative scenarios from `quickstart.md` §7: (a) misrouted `app_uuid` → HTTP 200, body `{"detail": "No matching IntegratedAgent.", "templates_updated": 0, "integrated_agents_inspected": 0}`; (b) misrouted `template_name` → HTTP 200, body `{"detail": "Template not found.", "templates_updated": 0, "integrated_agents_inspected": 1}`; (c) matched Template with `current_version=None` → HTTP 200, body `{"detail": "Template not found.", "templates_updated": 0, "integrated_agents_inspected": 1}`. Assert in all three cases that no Version row in the database was mutated

**Checkpoint**: All three user stories work independently. The webhook is feature-complete per the spec.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify the PR is merge-ready — all tests pass, coverage parity is maintained, lint is clean, and the quickstart smoke test runs end-to-end.

- [ ] T027 Run `poetry run python manage.py test retail.webhooks.templates` and assert all new tests pass with zero failures and zero errors
- [ ] T028 Run `poetry run coverage run manage.py test retail.webhooks.templates && poetry run coverage report -m --include="retail/webhooks/templates/usecases/direct_send_category.py,retail/webhooks/templates/views/direct_send_category.py,retail/webhooks/templates/serializers.py"` and confirm 100% line coverage on the three new production-code surfaces (no `# pragma: no cover` is required per plan.md §Constitution Check III — every branch is in-process exercisable)
- [ ] T029 Run `poetry run python contrib/compare_coverage.py` from the repo root and confirm it reports no decrease in project coverage (Constitution Principle III / `/home/paulobernardoaf/.cursor/rules/test-coverage-and-external-dependencies.mdc` Rule 1)
- [ ] T030 [P] Run `poetry run black --check retail/webhooks/templates/usecases/direct_send_category.py retail/webhooks/templates/views/direct_send_category.py retail/webhooks/templates/serializers.py retail/webhooks/templates/urls.py retail/webhooks/templates/tests/` and `poetry run flake8 retail/webhooks/templates/usecases/direct_send_category.py retail/webhooks/templates/views/direct_send_category.py retail/webhooks/templates/serializers.py retail/webhooks/templates/urls.py retail/webhooks/templates/tests/` on all new/modified files; fix any reported issues
- [ ] T031 Walk through `specs/003-template-category-webhook/quickstart.md` §§2–8 against a dev environment (or a local Django shell + an in-process HTTP client) and confirm each step's expected output matches the observed output — in particular the pre-flight `SELECT` (§2), the happy-path POST + audit log (§3), the dispatch-gate skip verification (§4), the replay no-op (§5), the three negative cases (§7), and the cross-tenant drill (§8)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately
- **Foundational (Phase 2)**: depends on Phase 1 — BLOCKS all user-story phases
- **User Story 1 (Phase 3, P1 — MVP)**: depends on Phase 2; no inter-story dependency
- **User Story 2 (Phase 4, P2)**: depends on Phase 2; touches the same `direct_send_category.py` file as US1 — recommended to land AFTER US1 so the early-return guard wraps an existing write site (T020 modifies the dispatch site introduced by T015)
- **User Story 3 (Phase 5, P3)**: depends on Phase 2; touches the same `direct_send_category.py` file as US1 — recommended to land AFTER US1 so the no-match / template-not-found branches wrap the existing fan-out site (T023/T024 modify the loop introduced by T015)
- **Polish (Phase 6)**: depends on all three user stories being complete

### Cross-Story Dependency Notes

- US1, US2, and US3 are **logically** independent (each story's acceptance criteria are testable in isolation) but they all extend the same single use case file (`retail/webhooks/templates/usecases/direct_send_category.py`). Within a team, they CAN be developed in parallel branches off Phase 2 and merged sequentially — each merge resolves a small conflict in the `execute()` body where the new branches plug in. The conflict surface is intentional (each branch is the right level of granularity for incremental delivery per the spec's user-story decomposition).
- Each story's tests land in the same two test files (`tests/usecases/test_direct_send_category.py` and `tests/views/test_direct_send_category.py`). Within a story the use-case tests and view tests CAN run in parallel ([P] tags on T017 vs T018; T021 vs T022 are not [P] because they touch the same file types but are within a single phase; T025 vs T026 likewise). Across stories the test additions are append-only and conflict-free.

### Within Each User Story

- Implementation tasks (T012–T016 for US1, T020 for US2, T023–T024 for US3) MUST land before the corresponding tests (use case → tests pattern, since the tests exercise the implementation directly without TDD).
- Within US1 specifically: T012–T015 are strictly sequential (they layer on the same file in dependency order: `_lookup_template` → `_evaluate_flagging_condition` + `_determine_flagging_reason` → `_flag_version` → fan-out loop in `execute`); T016 (`detail` string) can land in parallel with T015 if a developer is willing to merge in the same edit pass.

### Parallel Opportunities

- **Phase 1**: T001 / T002 / T003 — all three `__init__.py` creations are independent files, all [P]
- **Phase 2**: T009 (serializer) and T010 (view) — different files from T004–T008 (use case file) and from each other; both [P] against the use case work
- **Phase 3 (US1)**: T017 (use case tests) and T018 (view tests) — different test files, both [P]; T019 (integration test) shares the view test file with T018 so it cannot be [P] against it
- **Phase 6 (Polish)**: T030 (lint) is [P] against T027/T028/T029 (test + coverage) — different commands, no file conflicts

---

## Parallel Example: User Story 1

```bash
# After Phase 2 (Foundational) completes, the implementation tasks T012–T016 are
# sequential on retail/webhooks/templates/usecases/direct_send_category.py.
# Once T016 completes, launch both test tasks in parallel:

Task: "T017 Add use case unit tests in retail/webhooks/templates/tests/usecases/test_direct_send_category.py"
Task: "T018 Add view tests in retail/webhooks/templates/tests/views/test_direct_send_category.py"

# Then T019 (integration test) appends to the same view test file as T018:
Task: "T019 Add DirectSendCategoryWebhookDispatchIntegrationTest to retail/webhooks/templates/tests/views/test_direct_send_category.py"
```

---

## Implementation Strategy

### MVP-First Development Order (NOT a Shipping Cut-Line)

1. Complete Phase 1: Setup (3 trivial tasks, parallel)
2. Complete Phase 2: Foundational (8 tasks — the skeleton compiles, the endpoint returns HTTP 200 with zero counters)
3. Complete Phase 3: User Story 1 (8 tasks — flagging, fan-out, audit log, tests, integration with spec 002's dispatch gate)
4. **DEVELOPMENT CHECKPOINT (NOT a shipping checkpoint)**: Run `T017` + `T018` + `T019` tests, then walk through `quickstart.md` §3 (happy path) and §4 (dispatch skipped). The MVP slice is **unit-testable** here but **NOT spec-compliant** for shipping — FR-004b / FR-005 / FR-005a require WARNING-level audit lines (`no_matching_integrated_agent` / `template_not_found` / `template_has_no_current_version`) that US3 (T023/T024) lights up. Shipping a US1-only PR would silently violate three MUSTs from the spec.
5. **Continue with US2 + US3 before opening the shipping PR.** The PR title is `feat: add Direct Send template category webhook` (no "MVP" qualifier — the spec contract requires all three user stories to land together).

### Incremental Delivery (Development Increments — Single Shipping PR)

1. Setup + Foundational → skeleton compiles → endpoint exists, returns benign HTTP 200 (NOT spec-compliant for shipping)
2. + US1 → development MVP → demo: happy path flags template, dispatch gate skips (NOT spec-compliant for shipping — see C1 / Checkpoint above)
3. + US2 → replays clean up the audit-log noise → demo: same payload fired twice produces one `flagged` + one `flag_replay_noop` line (NOT spec-compliant for shipping)
4. + US3 → fail-closed for misrouted payloads → demo: misrouted `app_uuid` returns HTTP 200 with `no_matching_integrated_agent` audit line, no partial write (**spec-compliant — shipping cut-line**)
5. Each increment is a development-internal demo gate; the spec contract (FR-001 through FR-013) requires all three user stories to land in a single shipping PR. Later increments wrap earlier increments' logic in idempotency / fail-closed branches without breaking US1's tests.

### Parallel Team Strategy

With three developers (after Phase 2 lands):

- Developer A: User Story 1 (T012 → T013 → T014 → T015 → T016 → T017 + T018 in parallel → T019)
- Developer B: User Story 2 (T020 → T021 + T022) — waits for US1's T015 to land first since T020 modifies the dispatch site introduced by T015
- Developer C: User Story 3 (T023 + T024 → T025 + T026) — waits for US1's T015 to land first since T023/T024 modify the fan-out loop introduced by T015

Realistically, since US2 and US3 both depend on US1's dispatch site existing, the parallel structure collapses to "US1 first, then US2 + US3 in parallel". Three developers can still split the work — one on US1, two waiting to pick up US2 / US3 the moment US1's `execute()` body merges.

---

## Notes

- Every task targets a single, named file with a clear file path (no "src/[file]" placeholders).
- Every story has a single-paragraph **Goal** and an **Independent Test** that can be executed in isolation against a freshly-seeded fixture.
- Tests are MANDATORY (Constitution Principle III) — every new branch in every story is exercised by a unit test in the same task batch.
- The use case file (`retail/webhooks/templates/usecases/direct_send_category.py`) is the shared artifact across Phase 2 + all three stories; intra-story tasks on this file are strictly sequential. The serializer, view, urls, and test files are independent enough to support [P] markers where appropriate.
- No new database migration, no new env var, no new service / client layer (Decisions 7, 8 + `spec.md` §A10) — the PR ships ~6 files (3 production + 3 test files + 3 empty `__init__.py`).
- The legacy `TemplatesStatusWebhook` is read-only context for this feature — backfilling tests for it is captured as a follow-up PR (`plan.md` Complexity Tracking row 1).
