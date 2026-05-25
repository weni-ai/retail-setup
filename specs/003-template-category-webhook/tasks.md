---

description: "Task list for the Direct Send Template Incorrect-Category Webhook feature"
---

# Tasks: Direct Send Template Incorrect-Category Webhook

**Input**: Design documents from `/specs/003-template-category-webhook/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/direct-send-category-webhook.md`, `quickstart.md`

**Tests**: Tests are REQUIRED for this feature. The spec mandates test coverage per Constitution Principle III (`/home/paulobernardoaf/.cursor/rules/test-coverage-and-external-dependencies.mdc`) — every new branch added by this PR is exercised by a unit or integration test in the same PR.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested independently (delivered incrementally as an MVP slice).

## Spec-vs-implementation drift (read first)

`spec.md` was amended on **2026-05-25** with a clarification that
introduced **auto-demote** behavior on this webhook:

- A new `auto_demoted` token joins the FR-009a `event_name` enumeration.
- The previously-defined `no_action_required_already_flagged` token is
  **removed** from the spec.
- When the matched `current_version.status` is already `"FLAGGED"` AND
  the FR-006 flagging condition evaluates to **false** (the
  corrected-category signal — `template_category == template_correct_category == "UTILITY"`),
  the webhook now writes `status = "APPROVED"` (FR-006c / FR-007c
  clause (b) / FR-007d) and emits `auto_demoted` instead of being a
  no-op.

The current implementation under `retail/webhooks/templates/` still
reflects the **pre-clarification** behavior (uses
`NO_ACTION_REQUIRED_ALREADY_FLAGGED`, treats the `UTILITY/UTILITY` +
`FLAGGED` case as a write-skip no-op). The Phase 4 (US2) tasks below
re-task the auto-demote rework against the existing dispatch site;
they are the only `[ ]` (unchecked) implementation tasks remaining.

The companion design artifacts (`plan.md` §Summary + §Constraints
+ §Constitution Check III, `data-model.md` §1 + §5.2 + §5.4 + §6,
`contracts/direct-send-category-webhook.md` §2.3 + §4 + §6.2 +
§6.2a, `research.md` Decision 5 + "Decisions explicitly NOT taken",
`quickstart.md` §5 + §5.1 + §6 + §11) **have been resynced** to the
2026-05-25 clarification (T032 — completed; see checkbox below).
The only outstanding work for the spec-vs-implementation alignment
is the in-tree use-case + tests rework captured by T006, T020a,
T021, and T022.

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

- [X] T001 [P] Create empty `__init__.py` at `retail/webhooks/templates/tests/__init__.py`
- [X] T002 [P] Create empty `__init__.py` at `retail/webhooks/templates/tests/usecases/__init__.py`
- [X] T003 [P] Create empty `__init__.py` at `retail/webhooks/templates/tests/views/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Lay down the shared types (`DTO`, `Result`, `FlaggingReason`, `EventName`), the audit-log helper that enforces the `[DirectSendCategoryWebhook] event_name: k=v` shape (FR-009 / FR-009a–e), the use case skeleton with the `received` / `completed` / `unexpected_error` envelope (FR-009c, FR-010b), the inbound serializer (FR-003), the thin view (FR-001, FR-002), and the URL mount. Every user story depends on this skeleton being in place before per-story branches can be implemented.

**CRITICAL**: No user-story work can begin until Phase 2 is complete.

- [X] T004 Create `DirectSendCategoryDTO` (`@dataclass(frozen=True)` with `project_uuid: UUID`, `app_uuid: UUID`, `template_name: str`, `template_category: str`, `template_correct_category: str`) in new file `retail/webhooks/templates/usecases/direct_send_category.py` (Decision 9, data-model §5.1)
- [X] T005 Add `DirectSendCategoryResult` (`@dataclass(frozen=True)` with `templates_updated: int`, `integrated_agents_inspected: int`, `detail: str`, plus a `to_dict()` method whose keys are exactly `detail` / `templates_updated` / `integrated_agents_inspected`) to `retail/webhooks/templates/usecases/direct_send_category.py` (Decision 10, data-model §5.2, contract §2.1)
- [ ] T006 Update the `EventName(str, Enum)` in `retail/webhooks/templates/usecases/direct_send_category.py` to match the current spec FR-009a enumeration: **remove** `NO_ACTION_REQUIRED_ALREADY_FLAGGED = "no_action_required_already_flagged"` and **add** `AUTO_DEMOTED = "auto_demoted"`. Keep `FlaggingReason(str, Enum)` unchanged (`CATEGORY_MISMATCH`, `CATEGORY_NOT_UTILITY`, `CATEGORY_MISMATCH_AND_NOT_UTILITY` — pinned by FR-006b). The full FR-009a-aligned `EventName` token set is exactly the 10 values: `RECEIVED`, `FLAGGED`, `FLAG_REPLAY_NOOP`, `NO_ACTION_REQUIRED`, `AUTO_DEMOTED`, `NO_MATCHING_INTEGRATED_AGENT`, `TEMPLATE_NOT_FOUND`, `TEMPLATE_HAS_NO_CURRENT_VERSION`, `COMPLETED`, `UNEXPECTED_ERROR` (data-model §5.4 is currently stale on this — T032 brings the doc in sync)
- [X] T007 Add the audit-log helper to `retail/webhooks/templates/usecases/direct_send_category.py` — a single private `_emit(event: EventName, level: int, **kv)` method that formats every line as `[DirectSendCategoryWebhook] {event.value}: k1=v1 k2=v2 ...` and routes to `logger.{info,warning,error}` per the level argument; plus the three envelope helpers that fire on every well-formed request: `_emit_received` (INFO), `_emit_completed` (INFO), and `_emit_unexpected_error` (ERROR with `exc_info=True`). The seven per-IA outcome emit helpers are added by the user-story tasks that wire them — `_emit_flagged` by T014 (US1), `_emit_no_action_required` by T015 (US1), `_emit_flag_replay_noop` and `_emit_auto_demoted` by T020 (US2), and `_emit_no_matching_integrated_agent` / `_emit_template_not_found` / `_emit_template_has_no_current_version` by T023 / T024 (US3). Per FR-009b, the per-IA helpers added later MUST route at INFO for `flagged` / `flag_replay_noop` / `no_action_required` / `auto_demoted`, and at WARNING for `no_matching_integrated_agent` / `template_not_found` / `template_has_no_current_version`. The `_emit` method is the **only** place in the codebase that knows the log-line shape (Constitution Principle IV / plan.md §Constitution Check IV)
- [X] T008 Add `DirectSendCategoryWebhookUseCase` class to `retail/webhooks/templates/usecases/direct_send_category.py` with: (a) an `execute(dto: DirectSendCategoryDTO) -> DirectSendCategoryResult` method that emits `received` at start, calls the fully-implemented `_lookup_integrated_agents` from sub-clause (c), iterates over the resulting queryset with a fan-out loop body that is initially a `pass` placeholder (filled in by US1's T015), and emits `completed` at success-path exit; (b) an outer `try / except Exception as exc` block around the body that emits `unexpected_error` with `exc_info=True` and re-raises (so the view's 500 path is driven by the re-raise — FR-009b, FR-010b); (c) a `_lookup_integrated_agents(dto)` private method that returns `IntegratedAgent.objects.filter(project__uuid=dto.project_uuid, templates__versions__integrations_app_uuid=dto.app_uuid).distinct()` (Decision 2, data-model §2)
- [X] T009 [P] Add `DirectSendCategoryWebhookSerializer` (DRF `Serializer` subclass — NOT `ModelSerializer` — with `project_uuid = UUIDField(required=True)`, `app_uuid = UUIDField(required=True)`, `template_name = CharField(required=True, allow_blank=False)`, `template_category = CharField(required=True, allow_blank=False)`, `template_correct_category = CharField(required=True, allow_blank=False)`) to existing file `retail/webhooks/templates/serializers.py` (FR-003 / FR-003a — no allow-list on category values; contract §1.2). Do NOT declare a `Meta` class, do NOT add a `validate(self, attrs)` method that inspects or rejects unknown keys, and do NOT add per-field `choices=` constraints. The default DRF `Serializer` silently ignores unknown JSON keys — this is the forward-compatibility surface contract §1.3 / FR-003 last sentence mandate (if Integrations adds a new field like `detected_at` in a future release, Retail accepts the payload without a coordinated deploy). A `validate(attrs)` that rejects unknown keys would break the contract
- [X] T010 [P] Create `DirectSendCategoryWebhook` APIView in new file `retail/webhooks/templates/views/direct_send_category.py` — extends `rest_framework.views.APIView`, declares `permission_classes = [CanCommunicateInternally]` at class level, exposes a `post(self, request)` method that (1) instantiates `DirectSendCategoryWebhookSerializer(data=request.data)` and calls `serializer.is_valid(raise_exception=True)` — this call MUST stay OUTSIDE the try/except in step (5) so DRF's standard `ValidationError → HTTP 400` translation (FR-010a) is preserved, (2) builds a `DirectSendCategoryDTO(**serializer.validated_data)`, (3) instantiates the use case and calls `result = use_case.execute(dto)` — this single call is the ONLY statement wrapped by step (5)'s try/except, (4) returns `Response(result.to_dict(), status=HTTP_200_OK)`, (5) wraps **only** the `use_case.execute(dto)` call from step (3) in a `try / except Exception` that returns `Response({"detail": "Internal server error"}, status=HTTP_500_INTERNAL_SERVER_ERROR)` — wrapping the entire post body (e.g. including step 1's `is_valid(raise_exception=True)`) would silently convert validation errors into HTTP 500, breaking FR-010a (FR-001, FR-002, FR-010, FR-010b; Constitution Principle I — view is thin, no ORM, no business logic, no auth check in the body)
- [X] T011 Add URL entry `path("templates-status/api/category-notification/", DirectSendCategoryWebhook.as_view(), name="direct-send-category-webhook")` to `retail/webhooks/templates/urls.py` — preserve the existing `TemplatesStatusWebhook` entry verbatim (Decision 1, plan.md §Constraints "existing webhook untouched"). Import `DirectSendCategoryWebhook` from `retail.webhooks.templates.views.direct_send_category`

**Checkpoint**: skeleton compiles, URL is mounted, POSTing a valid payload returns HTTP 200 with `templates_updated=0` and `integrated_agents_inspected=0` (the fan-out loop body is still a placeholder). All three user stories can now be implemented in parallel.

---

## Phase 3: User Story 1 - Block dispatch when Integrations detects an incorrect template category (Priority: P1) — Development MVP Slice

**Goal**: When the webhook fires with a payload whose category fails the FR-006 two-clause check, every matched IntegratedAgent's Template has its `current_version.status` written to `"FLAGGED"`, the HTTP 200 response reports the counters, the audit log emits one `flagged` line per Version transitioned with the right `reason=` token, and the next broadcast attempt for the flagged template is skipped by spec 002's pre-existing dispatch gate.

**Independent Test**: With (a) a project that has at least one IntegratedAgent whose templates were created against a specific `app_uuid`, and (b) one of those templates having a current version in `APPROVED`, fire the webhook with `(project_uuid, app_uuid, template_name)` and `template_category="MARKETING"`. Verify (1) the Version's `status` is `FLAGGED`, (2) HTTP 200 response body reads `{"detail": "Templates flagged.", "templates_updated": 1, "integrated_agents_inspected": 1}`, (3) the audit log emits the three lines `received` / `flagged` (with `reason=category_not_utility`) / `completed`, and (4) a subsequent order-status webhook for the same template is skipped by `Broadcast.get_current_template`.

### Implementation for User Story 1

- [X] T012 [US1] Add `_lookup_template(integrated_agent, template_name)` private method to `retail/webhooks/templates/usecases/direct_send_category.py` returning `integrated_agent.templates.select_related("current_version").filter(name=template_name).first()` (Decision 4, FR-005 — case-sensitive exact match, eager-load `current_version` for the flagging-condition read)
- [X] T013 [US1] Add `_evaluate_flagging_condition(dto) -> bool` (returns `dto.template_category != dto.template_correct_category or dto.template_category != "UTILITY"`) and `_determine_flagging_reason(dto) -> FlaggingReason` (covers the four cells of the FR-006 / FR-006b truth table — composite reason when both clauses fire) to `retail/webhooks/templates/usecases/direct_send_category.py` (FR-006, FR-006a, FR-006b, data-model §5.3)
- [X] T014 [US1] Add `_flag_version(version, template, integrated_agent, dto, reason)` private method to `retail/webhooks/templates/usecases/direct_send_category.py` — captures `previous_status = version.status`, sets `version.status = "FLAGGED"`, calls `version.save(update_fields=["status"])` (FR-007b — `update_fields` is mandatory), and emits the `flagged` audit line via the helper from T007 carrying the full FR-009d `k=v` payload (`project_uuid`, `app_uuid`, `template_name`, `template_category`, `template_correct_category`, `integrated_agent_uuid`, `template_uuid`, `version_uuid`, `previous_status`, `new_status=FLAGGED`, `reason={reason.value}`). The early-return guard for `previous_status == "FLAGGED"` is added by US2 (T020) — for now this method always writes
- [X] T015 [US1] Replace the fan-out `pass` placeholder in `execute()` with the per-IA loop in `retail/webhooks/templates/usecases/direct_send_category.py`: for each `integrated_agent` returned by `_lookup_integrated_agents(dto)`, increment a local `inspected` counter, look up the template via `_lookup_template`, and when both the template and its `current_version` are non-None, branch on `_evaluate_flagging_condition(dto)` — if true, dispatch to `_flag_version` and increment a local `flagged` counter; if false, emit `no_action_required` via a new private `_emit_no_action_required(integrated_agent, template, version, dto)` method that wraps `self._emit(EventName.NO_ACTION_REQUIRED, INFO, **kv)` (FR-006 no-fire / FR-009a / FR-009b / FR-009d — carries `project_uuid`, `app_uuid`, `template_name`, `template_category`, `template_correct_category`, `integrated_agent_uuid`, `template_uuid`, `version_uuid`, `previous_status`). The `template_not_found` / `template_has_no_current_version` branches are added by US3 (T024); for the MVP slice, the loop deterministically skips those cases without raising
- [X] T016 [US1] Compute and pass the `detail` string into `DirectSendCategoryResult` at the end of `execute()` in `retail/webhooks/templates/usecases/direct_send_category.py` using the closed enumeration from data-model §5.2 / contract §2.3: track per-IA outcome tags during the fan-out, then map the set of observed outcomes to `"Templates flagged."` / `"Already flagged."` / `"No action required."` / `"No matching IntegratedAgent."` / `"Template not found."` / `"Mixed outcomes."`. The `"Already flagged."`, `"No matching IntegratedAgent."`, and `"Template not found."` branches do not fire under US1 alone — they require US2/US3 use case logic — but the mapping logic is added in full now so US2/US3 only have to wire the new outcome tags

### Tests for User Story 1

- [X] T017 [P] [US1] Add unit tests for `DirectSendCategoryWebhookUseCase` to new file `retail/webhooks/templates/tests/usecases/test_direct_send_category.py` covering: (a) single-IA flagging for each `FlaggingReason` variant — `category_mismatch` (`UTILITY` vs `MARKETING`), `category_not_utility` (`MARKETING` vs `MARKETING`), `category_mismatch_and_not_utility` (`MARKETING` vs `AUTHENTICATION`) — parametrized over `previous_status ∈ {"APPROVED", "PAUSED", "PENDING", "REJECTED", "DELETED"}`, asserting in every cell the Version's `status` is `"FLAGGED"` after the call, `Version.save` was called with `update_fields=["status"]`, the Template's `current_version_id` is unchanged after the call (FR-007a), and the `flagged` audit line carries the right `reason=` token and `previous_status=<starting value>`; (b) `UTILITY`/`UTILITY` payload → no-action path, no `Version.save` call, audit line is `no_action_required`; (c) multi-IA fan-out (US1 scenario 4) — two IAs with same `app_uuid` both get their Version flagged, `templates_updated=2`, `integrated_agents_inspected=2`; (d) cross-tenant exclusion (SC-006) — IA in project B with same `app_uuid` is excluded by the queryset, audit log makes no reference to it; (e) counter parity — the `templates_updated` and `integrated_agents_inspected` returned in the result equal the values emitted on the `completed` audit line; (f) `received` line is emitted exactly once at start with the full payload, `completed` line exactly once at end with the counters (FR-009c sequence); (g) FR-009e payload-key assertion — for each emitted log record across the happy path, assert `set(record.args.keys())` equals exactly the FR-009d-pinned keys for that event name (no extra keys leak from `validated_data`, no stray Retail-internal identifiers escape); (h) blocked-project still processes (spec.md Edge Cases row 12); (i) FR-009e no-truncation / no-redaction — fire a flagging payload with a 200-character `template_correct_category` value and assert the `flagged` audit line records the value verbatim
- [X] T018 [P] [US1] Add view-level HTTP tests for `DirectSendCategoryWebhook` to new file `retail/webhooks/templates/tests/views/test_direct_send_category.py` covering: (a) HTTP 200 happy path; (b) HTTP 401 — no `Authorization` header; (c) HTTP 403 — user lacks `can_communicate_internally`; (d) HTTP 400 — three sub-cases: missing required field, malformed UUID, blank string; (e) HTTP 500 — patch `DirectSendCategoryWebhookUseCase._lookup_integrated_agents` (a method invoked **inside** `execute()`, NOT `execute()` itself) to raise `Exception("db lost")` so the use case's outer `try / except Exception as exc` block from T008 runs and emits the audit line; assert (i) response body is `{"detail": "Internal server error"}`, (ii) an `unexpected_error` audit line was emitted with `exc_info=True` (FR-009b), (iii) a `received` line was emitted before the exception fired (FR-009c), and (iv) NO `completed` line was emitted (FR-009c last paragraph). Use `BaseTestMixin.setup_internal_user_permissions` (`retail/internal/test_mixins.py:130`) for auth setup
- [X] T019 [US1] Add integration test class `DirectSendCategoryWebhookDispatchIntegrationTest(TestCase)` to `retail/webhooks/templates/tests/views/test_direct_send_category.py` that exercises the cross-spec contract pinned by FR-013 / SC-002: (1) seed a project + IA + Template + `APPROVED` Version, (2) POST the webhook with a flagging payload, (3) re-fetch the Version and assert `status == "FLAGGED"`, (4) instantiate `retail.agents.domains.agent_webhook.services.broadcast.Broadcast` and call its `get_current_template(integrated_agent, lambda_data)` method with `lambda_data` shaped like a real order-status event whose `template` field matches the flagged template's name, (5) assert the return value is `None` (the dispatch gate skipped the flagged template). This pins the integration with spec 002's dispatch path without modifying it

**Checkpoint**: User Story 1 fully functional and independently unit-testable. The MVP slice is a **development checkpoint, NOT a shipping cut-line**: until US3 (T023/T024) lands, the silent-skip behavior on misrouted payloads violates FR-004b, FR-005, and FR-005a; until US2 (T020/T020a) lands, replays will (a) pollute the audit log with duplicate `flagged` lines, (b) issue redundant `Version.save(update_fields=["status"])` writes on every retry, AND (c) miss the auto-demote recovery path for corrected-category payloads (FR-006c / FR-007d). The shipping cut-line is after Phase 5 (US3) **plus** the auto-demote rework in Phase 4 — see Implementation Strategy below.

---

## Phase 4: User Story 2 - Webhook is safe to retry and replay (Priority: P2)

**Goal**: When the webhook is fired more than once for the same `(project_uuid, app_uuid, template_name)` tuple, the Version's `status` converges bidirectionally per the FR-008 contract: (i) flagging-payload replays converge on `FLAGGED` without redundant writes and emit `flag_replay_noop`, (ii) the **first** corrected-category replay (`UTILITY/UTILITY`) against a `FLAGGED` Version writes `APPROVED` and emits `auto_demoted` (FR-006c / FR-007d), and (iii) subsequent corrected-category replays (now against an `APPROVED` Version) follow the `no_action_required` path. The audit log distinguishes each replay class from the original transition.

**Independent Test**: With the same setup as US1, run two scenarios. **Scenario A** — fire the webhook twice with the same flagging payload (e.g. `MARKETING`/`MARKETING`). Verify (1) both responses are HTTP 200, (2) the first response's `templates_updated=1` and the second's `templates_updated=0`, (3) the audit log shows one `flagged` line (first call) and one `flag_replay_noop` line (second call) — both at INFO level, (4) `Version.save` was called exactly once across both requests. **Scenario B** — pre-seed the Version as `FLAGGED`, then POST `(template_category="UTILITY", template_correct_category="UTILITY")`. Verify (1) HTTP 200 with `templates_updated=0` and `detail="Auto-demoted."`, (2) the Version's `status` is `APPROVED` after the call, (3) the audit log emits one `auto_demoted` line at INFO with `previous_status=FLAGGED new_status=APPROVED`, (4) a subsequent POST of the same `UTILITY/UTILITY` payload returns `detail="No action required."` and does NOT re-write (FR-008 last clause).

### Implementation for User Story 2

- [X] T020 [US2] Add the **flag-replay** idempotency early-return guard to the flag-dispatch branch of the fan-out body introduced by US1 (T015) in `retail/webhooks/templates/usecases/direct_send_category.py`: when the FR-006 flagging condition is **true** AND the matched `version.status == "FLAGGED"`, dispatch to a new private `_emit_flag_replay_noop(integrated_agent, template, version, dto)` that wraps `self._emit(EventName.FLAG_REPLAY_NOOP, INFO, **kv)`, append a `"flag_replay_noop"` outcome tag, and `continue` without re-issuing the `Version.save`. The `flag_replay_noop` line carries the FR-009d payload (all five payload values + IA/Template/Version uuids + `previous_status=FLAGGED`, no `new_status` and no `reason` field). The local `flagged` counter is NOT incremented. Update the outcome-tag mapping from T016 so `"flag_replay_noop"` maps to `"Already flagged."` (Decision 5 — no dedup cache; FR-008a — no distributed lock)
- [ ] T020a [US2] Add the **auto-demote** write site to the non-flagging branch of the fan-out body in `retail/webhooks/templates/usecases/direct_send_category.py` (FR-006c / FR-007c clause (b) / FR-007d / FR-014, supersedes the previous `no_action_required_already_flagged` no-op): when the FR-006 flagging condition is **false** AND the matched `version.status == "FLAGGED"`, call a new private `_demote_version(version, template, integrated_agent, dto)` that captures `previous_status = version.status` ( `= "FLAGGED"` always on this branch), sets `version.status = "APPROVED"`, calls `version.save(update_fields=["status"])` (mirrors FR-007b — `update_fields` mandatory, single-row write), and emits `auto_demoted` via a new private `_emit_auto_demoted(integrated_agent, template, version, dto, previous_status)` that wraps `self._emit(EventName.AUTO_DEMOTED, INFO, **kv)` with the FR-009d payload (`project_uuid`, `app_uuid`, `template_name`, `template_category`, `template_correct_category`, `integrated_agent_uuid`, `template_uuid`, `version_uuid`, `previous_status=FLAGGED`, `new_status=APPROVED` — no `reason` field on `auto_demoted`). Append an `"auto_demoted"` outcome tag at the new demote call site **and remove the existing `"no_action_required_already_flagged"` outcome-tag append site introduced by T015's fan-out body** (currently at `direct_send_category.py:148-152`) — there is no longer a no-op outcome on the `FLAGGED + UTILITY/UTILITY` branch. Update the outcome-tag mapping from T016 so `"auto_demoted"` maps to a new `"Auto-demoted."` `detail` string and **delete the `"no_action_required_already_flagged" → "Already flagged."` entry from the `_OUTCOME_TO_DETAIL` map** (currently at `direct_send_category.py:99`). Increment the `templates_updated` counter (this branch is a write — it must be reflected in the counter parity with the `completed` log line per FR-010). **Remove** the now-unused `_emit_no_action_required_already_flagged` helper, the `NO_ACTION_REQUIRED_ALREADY_FLAGGED` enum value, and the `_handle_already_flagged(..., flagging_condition_met)` helper's non-flagging branch (the dispatch now splits inline at the two call sites — flag_replay_noop guard and demote guard — per the spec's revised FR-007c). The Template's `current_version` pointer MUST NOT be changed (only the status string is updated; FR-007a is preserved on the demote write)
- [ ] T021 [US2] Update unit tests in `retail/webhooks/templates/tests/usecases/test_direct_send_category.py` to match the post-T020a spec: (a) **rename** `IdempotentReplayWithNonFlaggingPayloadTest` → `AutoDemoteOnCorrectedCategoryTest`; (b) **rewrite** the renamed class's assertions to expect `version.status == "APPROVED"` after the call, `save_spy.call_count == 1`, `save_spy.last_call_kwargs["update_fields"] == ["status"]`, `result.templates_updated == 1`, `result.detail == "Auto-demoted."`, the audit log contains a single `auto_demoted` line at INFO with `previous_status=FLAGGED` and `new_status=APPROVED` (no `reason` key, no `new_status=FLAGGED`); (c) **update** the `EXPECTED_KEYS_BY_EVENT` constant at the top of the file — remove `EventName.NO_ACTION_REQUIRED_ALREADY_FLAGGED.value` entry, add an `EventName.AUTO_DEMOTED.value` entry whose key set is `{project_uuid, app_uuid, template_name, template_category, template_correct_category, integrated_agent_uuid, template_uuid, version_uuid, previous_status, new_status}` (FR-009d `auto_demoted` row); (d) keep `IdempotentReplayWithFlaggingPayloadTest` and `ConsecutiveCallsConvergeIdempotentlyTest` unchanged (the `flag_replay_noop` semantics are preserved by T020); (e) add a new `AutoDemoteSettlesIntoNoActionRequiredTest` that fires the `UTILITY/UTILITY` payload twice in a row against a pre-`FLAGGED` Version — assert (i) the first call writes `APPROVED` and emits `auto_demoted`, (ii) the second call observes `APPROVED` and emits `no_action_required` (NOT a second `auto_demoted` — FR-008 last sentence requires this convergence), (iii) `Version.save.call_count == 1` across both calls. Use `_VersionSaveSpy` to count writes
- [ ] T022 [US2] Update the view-level replay test in `retail/webhooks/templates/tests/views/test_direct_send_category.py`: (a) **rename** the existing replay test method to `test_corrected_category_replay_auto_demotes_to_approved`; (b) **rewrite** assertions — POST `UTILITY/UTILITY` against a pre-`FLAGGED` Version via the Django test client, assert HTTP 200, body `{"detail": "Auto-demoted.", "templates_updated": 1, "integrated_agents_inspected": 1}`, the Version is now `APPROVED` (re-fetch from DB); (c) **add** a new `test_flag_replay_with_same_payload_is_noop` view test that POSTs the same flagging payload (e.g. `MARKETING`/`MARKETING`) twice — assert the first response body has `templates_updated=1` / `detail="Templates flagged."` and the second has `templates_updated=0` / `detail="Already flagged."`, both HTTP 200, and the Version remains `FLAGGED` (pins FR-008 + SC-004). T022 is scoped to view-level happy-path assertions only — the FR-008 last-clause `UTILITY/UTILITY` settling-into-`no_action_required` convergence (post-demote replay against an `APPROVED` Version) is exercised by the use-case test added in T021(e) (`AutoDemoteSettlesIntoNoActionRequiredTest`) and is intentionally NOT duplicated at the view layer — the view test surface is bounded to the four HTTP outcome shapes (`Templates flagged.` / `Already flagged.` / `Auto-demoted.` / `No action required.`) and the auth + payload-validation boundary tests already covered by T018

**Checkpoint**: User Stories 1 AND 2 work independently. Replays converge bidirectionally — flagging-payload replays stay `FLAGGED` cleanly with `flag_replay_noop` audit lines and zero redundant writes; corrected-category replays demote `FLAGGED → APPROVED` exactly once via `auto_demoted` and settle into `no_action_required` on subsequent re-fires. The dispatch gate (spec 002's FR-007 / FR-012) re-admits demoted templates on the next broadcast attempt with no operator action required.

---

## Phase 5: User Story 3 - Misrouted or stale webhooks fail closed without partial writes (Priority: P3)

**Goal**: When the webhook payload references a project / app / template that Retail cannot locate, the response is HTTP 200, no Version row is mutated, and the audit log records the miss with the appropriate WARNING-level event (`no_matching_integrated_agent`, `template_not_found`, or `template_has_no_current_version`).

**Independent Test**: Fire the webhook three times — once with a `(project_uuid, app_uuid)` pair that matches no IntegratedAgent, once with a matching `(project_uuid, app_uuid)` but a `template_name` that no Template owns, and once with a matched Template whose `current_version` is `NULL`. Verify all three responses are HTTP 200, no Version's `status` changes, and the audit log emits one WARNING-level line per case with the right `event_name` token.

### Implementation for User Story 3

- [X] T023 [US3] Add the `no_matching_integrated_agent` branch to `execute()` in `retail/webhooks/templates/usecases/direct_send_category.py`: when the queryset returned by `_lookup_integrated_agents(dto)` is empty, short-circuit the fan-out, emit one `no_matching_integrated_agent` audit line at WARNING with only the five payload values (FR-009d — no IA/Template/Version identifiers because none were resolved), emit `completed` with `templates_updated=0` / `integrated_agents_inspected=0`, and return `DirectSendCategoryResult(templates_updated=0, integrated_agents_inspected=0, detail="No matching IntegratedAgent.")` (FR-004b)
- [X] T024 [US3] Add the `template_not_found` and `template_has_no_current_version` branches inside the fan-out loop in `retail/webhooks/templates/usecases/direct_send_category.py`: when `_lookup_template(integrated_agent, dto.template_name)` returns `None`, emit `template_not_found` at WARNING with `project_uuid` / `app_uuid` / `template_name` / `integrated_agent_uuid` (FR-005, FR-009d) and `continue` to the next IA (counter `inspected` is still incremented but `flagged` is not); when the template is found but its `current_version` is `None`, emit `template_has_no_current_version` at WARNING with `project_uuid` / `app_uuid` / `template_name` / `integrated_agent_uuid` / `template_uuid` (FR-005a, FR-009d) and `continue`. Extend the outcome-tag tracking from T016 so `"Template not found."` fires when every inspected IA produced either tag, and `"Mixed outcomes."` fires when the per-IA outcomes are not all the same

### Tests for User Story 3

- [X] T025 [US3] Add unit tests for the fail-closed branches to `retail/webhooks/templates/tests/usecases/test_direct_send_category.py` covering: (a) project exists but no IA has a Version with the requested `app_uuid` → audit line is `no_matching_integrated_agent` at WARNING with only the five payload values (assert no `integrated_agent_uuid` / `template_uuid` / `version_uuid` keys are present), result is `(0, 0, "No matching IntegratedAgent.")`; (b) project exists and IA matches but no Template named `template_name` → audit line is `template_not_found` at WARNING, no `Version.save` call, result is `(0, 1, "Template not found.")`; (c) project exists and IA matches and Template matches but `template.current_version is None` → audit line is `template_has_no_current_version` at WARNING, no `Version.save` call, result is `(0, 1, "Template not found.")`; (d) multi-IA fan-out with mixed outcomes (IA-1 flags, IA-2 has no Template) → two audit lines (`flagged` for IA-1, `template_not_found` for IA-2), result is `(1, 2, "Mixed outcomes.")` per contract §6.6. Assert WARNING level via `assertLogs(level="WARNING")`
- [X] T026 [US3] Add view-level fail-closed tests to `retail/webhooks/templates/tests/views/test_direct_send_category.py` covering the three negative scenarios from `quickstart.md` §7: (a) misrouted `app_uuid` → HTTP 200, body `{"detail": "No matching IntegratedAgent.", "templates_updated": 0, "integrated_agents_inspected": 0}`; (b) misrouted `template_name` → HTTP 200, body `{"detail": "Template not found.", "templates_updated": 0, "integrated_agents_inspected": 1}`; (c) matched Template with `current_version=None` → HTTP 200, body `{"detail": "Template not found.", "templates_updated": 0, "integrated_agents_inspected": 1}`. Assert in all three cases that no Version row in the database was mutated

**Checkpoint**: All three user stories work independently. The webhook is feature-complete per the spec.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify the PR is merge-ready — all tests pass after the Phase 4 rework, coverage parity is maintained, lint is clean, the design artifacts are back in sync with the spec, and the quickstart smoke test runs end-to-end.

- [ ] T027 Run `poetry run python manage.py test retail.webhooks.templates` and assert all new tests pass with zero failures and zero errors (must be re-run after T020a / T021 / T022 land — the current test suite still asserts the pre-clarification `no_action_required_already_flagged` behavior and will fail until T021 lands)
- [ ] T028 Run `poetry run coverage run --branch manage.py test retail.webhooks.templates && poetry run coverage report -m --include="retail/webhooks/templates/usecases/direct_send_category.py,retail/webhooks/templates/views/direct_send_category.py,retail/webhooks/templates/serializers.py"` and confirm 100% **branch** coverage on the three new production-code surfaces — including the new `_demote_version` / `_emit_auto_demoted` paths added by T020a (no `# pragma: no cover` is required per plan.md §Constitution Check III — every branch is in-process exercisable). Branch coverage (not just line coverage) is mandatory because the FR-006c / FR-007c / FR-007d dispatch matrix has four cells — (`version.status ∈ {APPROVED, FLAGGED}`) × (`flagging_condition ∈ {true, false}`) — and each cell MUST be exercised by at least one test. Line coverage alone would pass even if a cell never fired.
- [ ] T029 Run `poetry run python contrib/compare_coverage.py` from the repo root and confirm it reports no decrease in project coverage (Constitution Principle III / `/home/paulobernardoaf/.cursor/rules/test-coverage-and-external-dependencies.mdc` Rule 1)
- [ ] T030 [P] Run `poetry run black --check retail/webhooks/templates/` and `poetry run flake8 retail/webhooks/templates/` on all production and test files touched by this PR; fix any reported issues
- [ ] T031 Walk through `specs/003-template-category-webhook/quickstart.md` §§2–8 against a dev environment (or a local Django shell + an in-process HTTP client) and confirm each step's expected output matches the observed output — in particular the pre-flight `SELECT` (§2), the happy-path POST + audit log (§3), the dispatch-gate skip verification (§4), the flagging-payload replay (§5), the corrected-category auto-demote (§5.1), the operator-driven recovery channel (§6), the three negative cases (§7), and the cross-tenant drill (§8)
- [X] T032 [P] Re-sync the stale design artifacts to the 2026-05-25 spec clarification. **Completed** via the `/speckit-analyze` follow-up apply pass on 2026-05-25 — 19 `StrReplace` edits across `plan.md` (§Summary clause 4 + §Constraints "Two convergent demote channels" + §Constitution Check III event-name enumeration), `data-model.md` (§1 bidirectional write sites + §5.2 direction-agnostic counter + §5.2 `"Auto-demoted."` detail + §5.4 `AUTO_DEMOTED` enum + §6 read/write summary), `contracts/direct-send-category-webhook.md` (§2.3 outcome matrix + §4 bidirectional idempotency + §6.2 relabel + new §6.2a auto-demote example), `research.md` (Decision 5 two-path dispatch + rejected-alternative + "Decisions explicitly NOT taken" FR-014 flip), and `quickstart.md` (§5 forward-link + new §5.1 auto-demote walkthrough + §6 two-channel framing + §11 mapping table). Verified on 2026-05-25 by `rg --no-heading "no_action_required_already_flagged" specs/003-template-category-webhook/` returning hits **only** in (i) `tasks.md` lines 22 / 80 / 124 / 156 / 161 — every hit is an active TODO (T006 / T020a / T027) or this T032 self-citation, all of which describe the token's removal — and (ii) `spec.md:19` (Clarifications session 2026-05-25, the historical record of the removal). Zero stale references in `plan.md`, `data-model.md`, `contracts/direct-send-category-webhook.md`, `research.md`, or `quickstart.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately
- **Foundational (Phase 2)**: depends on Phase 1 — BLOCKS all user-story phases
- **User Story 1 (Phase 3, P1 — MVP)**: depends on Phase 2; no inter-story dependency
- **User Story 2 (Phase 4, P2)**: depends on Phase 2 AND on US1's T015 (the auto-demote + flag_replay_noop branches modify the dispatch site introduced by T015); T020a depends on T006 (the `AUTO_DEMOTED` enum value must exist before the helper that emits it)
- **User Story 3 (Phase 5, P3)**: depends on Phase 2; touches the same `direct_send_category.py` file as US1 — recommended to land AFTER US1 so the no-match / template-not-found branches wrap the existing fan-out site (T023/T024 modify the loop introduced by T015)
- **Polish (Phase 6)**: depends on all three user stories being complete; T032 is [P] against T027–T031 (different file scope)

### Cross-Story Dependency Notes

- US1, US2, and US3 are **logically** independent (each story's acceptance criteria are testable in isolation) but they all extend the same single use case file (`retail/webhooks/templates/usecases/direct_send_category.py`). Within a team, they CAN be developed in parallel branches off Phase 2 and merged sequentially — each merge resolves a small conflict in the `execute()` body where the new branches plug in. The conflict surface is intentional (each branch is the right level of granularity for incremental delivery per the spec's user-story decomposition).
- Each story's tests land in the same two test files (`tests/usecases/test_direct_send_category.py` and `tests/views/test_direct_send_category.py`). Within a story the use-case tests and view tests CAN run in parallel; across stories the test additions are append-only and conflict-free.

### Within Each User Story

- Implementation tasks (T012–T016 for US1, T020 / T020a for US2, T023–T024 for US3) MUST land before the corresponding tests (use case → tests pattern, since the tests exercise the implementation directly without TDD).
- Within US1 specifically: T012–T015 are strictly sequential; T016 (`detail` string) can land in parallel with T015 if a developer is willing to merge in the same edit pass.
- Within US2 specifically: T006 (enum update) MUST land before T020a (the helper consumes the new `AUTO_DEMOTED` value); T020 (flag-replay guard) MUST land before T020a (auto-demote write) — both modify the same `if version.status == FLAGGED:` dispatch site introduced by T015, and the diff hygiene is cleaner if the flag-replay branch lands first (T020 leaves the `else` clause as the deprecated `_handle_already_flagged` no-op call; T020a then replaces that `else` clause with the inline `_demote_version` dispatch); T020 (flag_replay_noop guard) and T020a (auto-demote write) MUST both land before T021 / T022 so the test suite can assert the new dual-path behavior.

### Parallel Opportunities

- **Phase 1**: T001 / T002 / T003 — all three `__init__.py` creations are independent files, all [P]
- **Phase 2**: T009 (serializer) and T010 (view) — different files from T004–T008 (use case file) and from each other; both [P] against the use case work
- **Phase 3 (US1)**: T017 (use case tests) and T018 (view tests) — different test files, both [P]; T019 (integration test) shares the view test file with T018 so it cannot be [P] against it
- **Phase 4 (US2)**: T021 (use case tests) and T022 (view tests) — different test files; both can be developed in parallel once T020a lands
- **Phase 6 (Polish)**: T030 (lint) and T032 (doc resync) are [P] against T027/T028/T029 (test + coverage) — different commands / file scopes, no conflicts

---

## Parallel Example: User Story 2 (the auto-demote rework)

```bash
# After Phase 2's T006 (enum update) lands, the T020 / T020a sequence is
# sequential on retail/webhooks/templates/usecases/direct_send_category.py.
# Once T020a completes, launch both test tasks in parallel:

Task: "T021 Update use case unit tests in retail/webhooks/templates/tests/usecases/test_direct_send_category.py"
Task: "T022 Update view-level replay tests in retail/webhooks/templates/tests/views/test_direct_send_category.py"

# In parallel with the test work, the doc resync (T032) can also land:
Task: "T032 Re-sync plan.md / data-model.md / contracts/ / research.md / quickstart.md to the 2026-05-25 spec clarification"
```

---

## Implementation Strategy

### MVP-First Development Order (NOT a Shipping Cut-Line)

1. Complete Phase 1: Setup (3 trivial tasks, parallel)
2. Complete Phase 2: Foundational (8 tasks — the skeleton compiles; T006 lands the enum update from the 2026-05-25 clarification)
3. Complete Phase 3: User Story 1 (8 tasks — flagging, fan-out, audit log, tests, integration with spec 002's dispatch gate)
4. **DEVELOPMENT CHECKPOINT (NOT a shipping checkpoint)**: Run `T017` + `T018` + `T019` tests, then walk through `quickstart.md` §3 (happy path) and §4 (dispatch skipped). The MVP slice is **unit-testable** here but **NOT spec-compliant** for shipping — FR-004b / FR-005 / FR-005a / FR-006c / FR-007d each MUST audit lines or auto-demote writes that the MVP slice does not emit. Shipping a US1-only PR would silently violate four MUSTs from the spec.
5. **Continue with US2 + US3 before opening the shipping PR.** The PR title is `feat: add Direct Send template category webhook` (no "MVP" qualifier — the spec contract requires all three user stories to land together).

### Incremental Delivery (Development Increments — Single Shipping PR)

1. Setup + Foundational → skeleton compiles → endpoint exists, returns benign HTTP 200 (NOT spec-compliant for shipping)
2. + US1 → development MVP → demo: happy path flags template, dispatch gate skips (NOT spec-compliant for shipping)
3. + US2 (T020 + T020a) → replays converge bidirectionally → demo: (a) flagging payload fired twice produces one `flagged` + one `flag_replay_noop`; (b) corrected-category payload against a pre-`FLAGGED` Version emits `auto_demoted` and writes `APPROVED`; (c) re-firing the corrected-category payload converges into `no_action_required` (NOT spec-compliant for shipping until US3 lands too)
4. + US3 → fail-closed for misrouted payloads → demo: misrouted `app_uuid` returns HTTP 200 with `no_matching_integrated_agent` audit line, no partial write (**spec-compliant — shipping cut-line**)
5. Each increment is a development-internal demo gate; the spec contract (FR-001 through FR-014) requires all three user stories to land in a single shipping PR. Later increments wrap earlier increments' logic in idempotency / auto-demote / fail-closed branches without breaking US1's tests.

### Parallel Team Strategy

With three developers (after Phase 2 lands):

- Developer A: User Story 1 (T012 → T013 → T014 → T015 → T016 → T017 + T018 in parallel → T019)
- Developer B: User Story 2 (T020 → T020a → T021 + T022 → T032 in parallel) — waits for US1's T015 to land first since T020 / T020a modify the dispatch site introduced by T015
- Developer C: User Story 3 (T023 + T024 → T025 + T026) — waits for US1's T015 to land first since T023/T024 modify the fan-out loop introduced by T015

Realistically, since US2 and US3 both depend on US1's dispatch site existing, the parallel structure collapses to "US1 first, then US2 + US3 in parallel". Three developers can still split the work — one on US1, two waiting to pick up US2 / US3 the moment US1's `execute()` body merges.

---

## Notes

- Every task targets a single, named file with a clear file path (no "src/[file]" placeholders).
- Every story has a single-paragraph **Goal** and an **Independent Test** that can be executed in isolation against a freshly-seeded fixture.
- Tests are MANDATORY (Constitution Principle III) — every new branch in every story is exercised by a unit test in the same task batch.
- The use case file (`retail/webhooks/templates/usecases/direct_send_category.py`) is the shared artifact across Phase 2 + all three stories; intra-story tasks on this file are strictly sequential. The serializer, view, urls, and test files are independent enough to support [P] markers where appropriate.
- No new database migration, no new env var, no new service / client layer (Decisions 7, 8 + `spec.md` §A10) — the PR ships ~6 production / test files + 3 empty `__init__.py`s; the 5 design-artifact doc-resync edits were applied as part of T032 (now complete) and ship as part of the same PR.
- The legacy `TemplatesStatusWebhook` is read-only context for this feature — backfilling tests for it is captured as a follow-up PR (`plan.md` Complexity Tracking row 1).
- The auto-demote rework (T006, T020a, T021, T022) is the only outstanding implementation work as of this tasks.md regeneration; T001–T005, T007–T020, T023–T026 are already complete in the codebase and align with the current spec. T032 (design-artifact resync) is complete; T027–T031 (test run, coverage, lint, quickstart walkthrough) remain as the polish gate before the PR opens.
