---

description: "Tasks for WhatsApp Direct Send Broadcasts (OrderStatus)"
---

# Tasks: WhatsApp Direct Send Broadcasts (OrderStatus)

**Input**: Design documents from `/specs/002-direct-send-broadcasts/`

**Prerequisites**: `plan.md` (required), `spec.md` (required), `research.md`, `data-model.md`, `contracts/`

**Tests**: This project's constitution mandates test coverage parity (Principle III — NON-NEGOTIABLE), so every new branch is exercised by tests in the same PR. Tests are listed FIRST within each user story (TDD discipline) and MUST fail before the matching implementation task is run.

**Organization**: Tasks are grouped by user story (US1 → US4) so each story can be implemented and tested independently. After Phase 2 completes, all four user stories can be worked on in parallel.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Maps to a user story (US1, US2, US3, US4)
- File paths are relative to the repository root.

### Status marker legend

- `[ ]` — Pending.
- `[X]` — Completed and canonical.
- `[~]` — **Superseded**: the work was performed during an earlier phase but the canonical merge shape was relocated by a later phase (currently used by Phase 3.5's relocation of `direct_send` from a model column to `IntegratedAgent.config` JSON). A `[~]` task MUST NOT be re-executed on a fresh checkout; follow the explicit `SUPERSEDED by T...` cross-reference instead.

## Path Conventions

- Production code under `retail/<app>/...`
- Tests collocated under `retail/<app>/tests/...` (matches the project's existing layout — see `plan.md` Project Structure section).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify the working environment is on the right branch and the existing test suite is green before any change is made.

- [X] T001 Verify branch `002-direct-send-broadcasts` is checked out, then capture the baseline coverage report by running `poetry run coverage run manage.py test && poetry run coverage report -m | tee /tmp/baseline_coverage.txt`. The output is the reference for the parity check at the end (Phase 7).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema changes, status enum extension, and shared exceptions every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

> **Spec correction — read before acting on T002/T003/T009a**:
> the `direct_send` column approach captured below was **superseded
> by `data-model.md §1`**. The flag is stored inside the existing
> `IntegratedAgent.config` JSONField; no column ships and no agents
> migration is generated. Tasks T002/T003/T009a are preserved
> verbatim for git-history continuity but their effect is undone by
> Phase 3.5 (T100–T106). A fresh implementer MUST treat T002 as a
> no-op (do NOT add the field) and skip T003/T009a's agents-migration
> steps; T004/T005/T006/T007/T007a/T008 remain authoritative for the
> templates side.
>
> **⚠️ Checkmark interpretation (T002 / T003 / T009a)**: the `[X]`
> markers below mean "the column-style work was DONE locally during
> US1 implementation", NOT "this is the canonical merge shape". The
> canonical merge shape is delivered by Phase 3.5 (T100–T106) which
> relocates the flag to `IntegratedAgent.config["direct_send"]`. A
> reviewer scanning Phase 2 checkmarks for completion status MUST
> read the inline `**⚠️ Superseded by ...**` notes on each affected
> task AND confirm Phase 3.5 has been executed before merge.
>
> **⚠️ Phase 3.5 ordering**: Phase 3.5 (T100–T106) sits between
> Phase 3 (US1) and Phase 4 (US2) in execution order. It **MUST run
> BEFORE Phase 4 (US2)** so US2 fixtures (T015–T019) and the US2
> Direct Send branch implementation (T026–T028) are authored against
> the canonical `IntegratedAgent.config["direct_send"]` JSON-key form
> from the start, AND **MUST run BEFORE Phase 7 (T036–T039)** so the
> coverage parity check (T037) and PR creation (T039) ship the
> corrected storage scheme. The execution-order rule is restated in
> `Dependencies & Execution Order → Phase Dependencies` below.

- [~] T002 **⚠️ SUPERSEDED by T101 (Phase 3.5)** — Original task body: Add `direct_send = models.BooleanField(default=False)` to `IntegratedAgent` in `retail/agents/domains/agent_integration/models.py` (data-model.md §1; research Decision 1 / Decision 13). **The `[~]` marker means "done locally during US1, then UNDONE by Phase 3.5"**; the canonical merge shape is the JSON-key form (T101). Do not add this field on a fresh checkout.
- [~] T003 **⚠️ SUPERSEDED by T100 (Phase 3.5)** — Original task body: Generate the migration for T002: `poetry run python manage.py makemigrations agents --name integratedagent_direct_send`. Output file: `retail/agents/migrations/00XX_integratedagent_direct_send.py`. **The `[~]` marker means "no agents migration ships"**; do not generate this file on a fresh checkout.
- [X] T004 Extend `Version.STATUS_CHOICES` in `retail/templates/models.py` with `("PAUSED", "Paused")` and `("FLAGGED", "Flagged")` at the end of the existing tuple (data-model.md §2; FR-006).
- [X] T005 Generate the migration for T004: `poetry run python manage.py makemigrations templates --name alter_version_status_paused_flagged`. Output file: `retail/templates/migrations/0017_alter_version_status_paused_flagged.py`.
- [X] T006 [P] Extend `UpdateTemplateData.status` `Literal[...]` in `retail/templates/usecases/update_template.py` to include `"PAUSED"` and `"FLAGGED"` (data-model.md §2 last sub-section).
- [X] T007 [P] Add the two custom exceptions in `retail/agents/domains/agent_integration/exceptions.py`, both inheriting from `rest_framework.exceptions.APIException` with `status_code = status.HTTP_422_UNPROCESSABLE_ENTITY` (matches the existing `GlobalRuleUnprocessableEntity` pattern in the same file): `DirectSendTemplateUnavailableError(template_name, requested_language, fallback_language, reason)` with `default_code = "direct_send_template_unavailable"` and `DirectSendUnsupportedComponentError(template_name, component_type)` with `default_code = "direct_send_unsupported_component"`. Each exception MUST implement an explicit `__init__(self, *, template_name, ...)` that (a) stores every constructor kwarg on `self` (e.g. `self.template_name = template_name`) so tests and structured logging can read them back as documented in `data-model.md §5`, and (b) builds a human-readable `detail` string from the kwargs (e.g. `f"Template {template_name} is not available in {requested_language} or fallback locale {fallback_language}: {reason}"`) and forwards it to `super().__init__(detail=detail, code=self.default_code)` so DRF surfaces both the `detail` and the stable `code` documented in `quickstart.md §7`. DRF auto-translates the raised exception to a 422 response (with the `code` field set to `default_code` in the JSON body); no view-side try/except is required (data-model.md §5; research Decision 5 / Decision 12).
- [X] T007a [P] Create the Direct Send length-limit constants module in `retail/agents/domains/agent_webhook/services/direct_send_constants.py` with `MAX_BODY_LENGTH = 1024`, `MAX_HEADER_TEXT_LENGTH = 60`, `MAX_FOOTER_LENGTH = 60`, `MAX_BUTTON_LABEL_LENGTH = 20` (Meta's documented per-component limits per `contracts/meta-library-catalog.md` §5 and `contracts/messaging-gateway-payload.md` §3.1). Add a module-level docstring stating that `MAX_BUTTON_LABEL_LENGTH` is named generically because it bounds BOTH `cta_url.display_text` (the visible button label, not the URL itself — which can be much longer) AND `reply.title`; if Meta ever updates either limit independently, split into `MAX_CTA_DISPLAY_TEXT_LENGTH` + `MAX_REPLY_TITLE_LENGTH` (same value at v1). T012 (US1, dispatch-time post-substitution check) and T023 (US2, fetch-time pre-substitution check) both import from this module so the limits have a single source of truth.
- [X] T008 Apply the migrations: `poetry run python manage.py migrate` (depends on T003 and T005).
- [X] T009 Run the existing test suite to confirm the schema changes did not break any test: `poetry run python manage.py test`. Any pre-existing failure must be fixed in this task before moving on.
- [X] T009a Verify migration reversibility for the single migration this feature ships (FR-025). **⚠️ Agents-side half SUPERSEDED by Phase 3.5** — only the `templates` rollback runs; there is no agents migration to roll back (see T100). The canonical (post-correction) command is:

  ```bash
  poetry run python manage.py migrate templates <previous_templates_migration> \
    && poetry run python manage.py migrate
  ```

  The migration MUST round-trip cleanly (no schema drift, no data loss). `templates.0017_alter_version_status_paused_flagged` is a pure `AlterField` on the `STATUS_CHOICES` tuple; no foreign key is introduced or modified, so rollback order is unconstrained. Future migrations that DO touch FKs would require a stricter order (drop FK-holder side first); flag that explicitly when the next coupled migration lands. This task proves the rollback story documented in `quickstart.md §9`.

  **Agents-side half: no-op.** The original task body chained an `agents` rollback for the `direct_send` column draft (T002/T003), but Phase 3.5 (T100) confirmed no agents migration was ever generated. The agents-side rollback command is therefore omitted entirely — there is nothing to roll back. **⚠️ Superseded by `quickstart.md §9` rewrite** retained for git-history continuity.

**Checkpoint**: Foundation ready — User Stories 1–4 can now begin in parallel.

---

## Phase 3: User Story 1 — Dispatch order-status broadcast through Direct Send (Priority: P1) 🎯 MVP

**Goal**: When the rule engine returns a template + variables for a Direct Send-enabled `IntegratedAgent`, Retail substitutes every `{{N}}` placeholder server-side and sends Flows the new `msg.direct_send: true` payload (see `contracts/messaging-gateway-payload.md` §3).

**Independent Test**: With a fixture `IntegratedAgent` whose `direct_send=True` and a `Template` whose `current_version.status="APPROVED"` and metadata carries body/header/footer/buttons, fire `Broadcast.build_message(integrated_agent, lambda_data)` and assert the returned dict matches the Direct Send shape, with all `{{N}}` placeholders replaced by the values from `lambda_data["template_variables"]` and the Direct Send identifier set to `template.current_version.template_name`.

### Tests for User Story 1 (TDD — write FIRST, ensure FAIL before implementation)

- [X] T010 [P] [US1] Tests for `direct_send_payload_builder` in `retail/agents/tests/services/test_direct_send_payload_builder.py` covering: variable substitution with `{{1}}`/`{{2}}` replaced from a positional dict (regex `\{\{\s*(\d+)\s*\}\}`, whitespace-tolerant), missing-index logs WARNING and substitutes empty string, extra-index silently ignored (spec edge cases); `is_valid_direct_send_template_name` returns True for snake_case names ≤512 chars and False for names with hyphens/uppercase/length>512 (research Decision 7).
- [X] T011 [P] [US1] **Happy-path wire shape** — Tests for `Broadcast.build_direct_send_message` in `retail/agents/tests/services/test_broadcast_direct_send.py` covering Story 1 AS1, AS2, AS3. **AS1**: body with `{{1}}`/`{{2}}` substituted, `template.locale` from template metadata, `template.name` equals `Version.template_name`, `msg["direct_send"] is True`, `msg["category"] == "utility"` — Python dict notation; the wire JSON renders these as `"direct_send": true` and `"category": "utility"` per `contracts/messaging-gateway-payload.md` §3.1. **AS2**: image header + CTA URL button, URL with `{{1}}` substituted, `msg.header.image_url` AND `msg.attachments[0]` both set to the same value per contract §3.1 / §3.2. **AS3**: body-only template, no buttons / header / footer / variables.
- [X] T011a [P] [US1] **Quick-reply buttons** — Tests in the same file (`test_broadcast_direct_send.py`) covering quick-reply button rendering: up to 3 `QUICK_REPLY` buttons rendered with `sub_type="reply"`, `id`, `title` per contract §3.3; at least one title contains `{{1}}` and is substituted via the helper (Decision 6). Assert the resulting button list preserves order and that titles ≤ 20 chars survive the post-substitution length gate from T013.
- [X] T011b [P] [US1] **Refusal — naming-rule violation** — Tests in the same file covering the FR-017 skip path: a template whose `Version.template_name` contains uppercase / hyphens / non-ASCII characters or exceeds 512 chars MUST cause `build_direct_send_message` to return `None` AND emit the audit log line `[BroadcastDispatch] skipped_due_to_direct_send_validation: project_uuid={integrated_agent.project.uuid} agent={...} template={...} reason=naming_rule event={data}` (FR-039 mandates `project_uuid` as a top-level key; Decision 7). Capture with `assertLogs` at WARNING level and assert the literal `reason=naming_rule` substring is present.
- [X] T011c [P] [US1] **Refusal — empty body / length limits** — Tests in the same file covering the contract §4 rule-2 and rule-3 refusal paths: (i) `template.metadata.body` missing or empty → `None` + audit log with `reason=empty_body` (`contracts/messaging-gateway-payload.md` §4 rule 2); (ii) post-substitution component length-limit overflow → `None` + audit log with `reason=component_length_limit` when the substituted body > 1024, header.text > 60, footer > 60, button `display_text` (cta_url) > 20, or button `title` (reply) > 20 (constants from `direct_send_constants.py`); (iii) button `url` is NOT length-checked at this gate — a substituted URL > 20 chars MUST dispatch normally (URLs can be up to 2000 chars per `contracts/messaging-gateway-payload.md` §3.3). All log lines carry `project_uuid` as a top-level key per FR-039.
- [X] T011d [P] [US1] **No-local-template edge case** — Test in the same file covering the spec edge case "Direct Send-enabled agent with no local template for the rule": given a Direct Send-enabled `IntegratedAgent` and a `data["template"]` that does NOT exist in `integrated_agent.templates`, `Broadcast.build_message` returns `None`, `build_direct_send_message` is never invoked, no payload is built, no `BroadcastMessage` row is persisted, and a `WARNING` line matching the substring `"not found"` is emitted by the dispatch flow (FR-027 — after US3's T031 consolidation, this assertion is satisfied by `Broadcast.build_message`'s downstream "Template not found or has no approved current version" line, which remains the legacy shape; the upstream `Broadcast.get_current_template` per-name miss now emits the unified `[BroadcastDispatch] skipped_due_to_status: ... version_status=NOT_FOUND ...` audit shape per FR-039's "Dispatch-gate skip (unified shape)" entry).
- [X] T011e [P] [US1] **BroadcastMessage persistence parity** — End-to-end test in `retail/agents/tests/services/test_broadcast_direct_send_persistence.py` (sibling to `test_broadcast_direct_send.py` so the persistence-focused fixtures stay separated from the wire-shape fixtures and the file does not grow past comfortable review size) that drives `Broadcast.build_message` → existing dispatch wiring against a Direct Send-enabled fixture and asserts (a) a `BroadcastMessage` row is persisted with the expected `status`, `template_name`, `contact_urn`, and `integrated_agent` on the happy path (FR-016, SC-005); (b) NO `BroadcastMessage` row is persisted on EACH refusal class exercised by T011b–T011c (naming-rule, empty body, length limit — contract §4). Use a mocked `flows_service.send_whatsapp_broadcast` to capture (a)'s outbound call without hitting Flows.

### Implementation for User Story 1

- [X] T012 [US1] Create `retail/agents/domains/agent_webhook/services/direct_send_payload_builder.py` with: `substitute_template_variables(text: str, variables: Dict[str, Any], *, template_name: str) -> str` (regex `\{\{\s*(\d+)\s*\}\}` — whitespace-tolerant; missing index→`""` + WARNING log, extra index→ignored); `is_valid_direct_send_template_name(name: str) -> bool` (regex `^[a-z0-9_]+$`, length ≤ 512); helper builders for header / footer / buttons that consume the `Template.metadata` shape produced by `_get_template_info`. Import the Direct Send length-limit constants (`MAX_BODY_LENGTH`, `MAX_HEADER_TEXT_LENGTH`, `MAX_FOOTER_LENGTH`, `MAX_BUTTON_LABEL_LENGTH`) from `retail/agents/domains/agent_webhook/services/direct_send_constants.py` (created in T007a) so T013 (post-substitution dispatch-time check) and T023 (pre-substitution assignment-time check) share the same source of truth (research Decision 6 / Decision 8; contracts/meta-library-catalog.md §5).
- [X] T013 [US1] Implement `Broadcast.build_direct_send_message` in `retail/agents/domains/agent_webhook/services/broadcast.py` matching the shape in `contracts/messaging-gateway-payload.md` §3: substitute body / header.text / footer / buttons[*].url / buttons[*].title via the helper; when `template.metadata["header"]["type"] == "IMAGE"`, set `msg.header = {"type": "image", "image_url": data["template_variables"]["image_url"]}` AND append `f"image/jpeg:{image_url}"` (mirroring the s3-keyed shape produced by `build_broadcast_template_message`) to `msg.attachments` for downstream parity — both representations are required by contracts/messaging-gateway-payload.md §3.1 ("`attachments`: conditional — required when `header.type == "image"`") and §3.2 ("Same value MUST also appear in `msg.attachments[0]`"); emit `msg.direct_send=true`, `msg.category="utility"`; refuse to emit (return `None` + audit-log entry with format `[BroadcastDispatch] skipped_due_to_direct_send_validation: project_uuid={integrated_agent.project.uuid} agent={...} template={...} reason={naming_rule|empty_body|component_length_limit} event={data}` — FR-039 mandates `project_uuid` as a top-level key) when (a) the template name fails `is_valid_direct_send_template_name`, (b) `template.metadata.body` is missing/empty, or (c) any post-substitution component exceeds Meta's documented length limits — body ≤ `MAX_BODY_LENGTH` (1024), header.text ≤ `MAX_HEADER_TEXT_LENGTH` (60), footer ≤ `MAX_FOOTER_LENGTH` (60), button `display_text` (cta_url) and button `title` (reply) ≤ `MAX_BUTTON_LABEL_LENGTH` (20). Note: button `url` is NOT subject to the 20-char limit per `contracts/messaging-gateway-payload.md` §3.3 — `display_text` is the only `cta_url` field with a 20-char ceiling, and the URL itself can be much longer (Meta allows up to 2000 chars). Reuse the length constants from `direct_send_constants.py` (T007a) so the dispatch-time limits and the assignment-time validation (T023) share a single source of truth.
- [X] T014 [US1] Branch `Broadcast.build_message` in `retail/agents/domains/agent_webhook/services/broadcast.py` so that when `integrated_agent.direct_send` is `True` it calls `build_direct_send_message`; otherwise it keeps calling the existing `build_broadcast_template_message` unchanged (research Decision 11). No changes are required to `Broadcast.send_message` (`retail/agents/domains/agent_webhook/services/broadcast.py:391`) — it consumes the result of `build_message` only via `message.get("msg", {}).get("template", {}).get("name", ...)` for logging, then forwards the entire `message` dict to `flows_service.send_whatsapp_broadcast(message)`. The Direct Send payload preserves both `msg.template` and `msg.template.name` (per `contracts/messaging-gateway-payload.md` §3.1), so `send_message` is generic over the new dict shape and the `BroadcastMessage` persistence path (`_register_broadcast_event` + `_record_broadcast_message`) works unchanged. T011e's "end-to-end build_message → existing dispatch wiring" assertion is satisfied without modifying `send_message`.
- [X] T014a [P] [US1] Add a regression test for FR-028 duplicate-trigger suppression on the Direct Send path in `retail/agents/tests/usecases/test_order_status_dedup_direct_send.py`. With a Direct Send-enabled `IntegratedAgent` fixture and `@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "test-direct-send-dedup"}})` (Constitution Principle III), invoke `AgentOrderStatusUpdateUsecase.execute(...)` twice in a row with the SAME canonical idempotency tuple `(Project, IntegratedAgent.uuid, OrderStatusDTO.orderId, OrderStatusDTO.currentState)` (the `Project` component is identified by its FK integer or UUID per FR-028's serialization rule). Assert: (a) exactly one outbound `flows_service.send_whatsapp_broadcast` call is made (mocked with `MagicMock(spec=...)`); (b) exactly one `BroadcastMessage` row is persisted; (c) the second invocation emits the INFO log shape `[ORDER_STATUS] duplicate_skipped: vtex_account={...} agent_uuid={...} current_state={...} order_id={...}` (captured with `assertLogs` at INFO level — FR-039 dedup-skip shape); (d) **dedup cache key shape (FR-029 normative components)** — wrap `django.core.cache.cache.add` with `unittest.mock.patch("django.core.cache.cache.add", wraps=cache.add)` (or capture via a `MagicMock(side_effect=cache.add)` on the import alias used in `_is_duplicate_event`), invoke `execute` once more with a fresh tuple, and assert the captured positional `cache_key` argument matches the regex `^order_status_event:[^:]+:[0-9a-f-]{36}:[^:]+:[^:]+$` AND that splitting on `:` yields exactly five segments — the literal prefix plus the four normative components `(project, integrated_agent.uuid, order_id, current_state)`. The second segment intentionally uses `[^:]+` (rather than `\d+`) so the test passes whether the implementation serializes `project` as the FK integer (`project_id`) or as the UUID — both are spec-compliant per FR-028's serialization rule. This pins FR-028 + FR-029 + FR-030 + FR-039's dedup-skip shape for the Direct Send cohort. Without (d), a future refactor that scopes the dedup key by `direct_send` (or drops `current_state`, or adds a fifth component, or removes one of the four) would silently invalidate the spec's "components are normative" claim and would not be caught by any other test. **Legacy-cohort coverage** (FR-028 last sentence — "applies identically to the Direct Send path and the legacy path"): the legacy cohort is already covered by the pre-feature dedup tests in `retail/agents/tests/usecases/test_order_status_update.py` (`test_execute_skips_duplicate_event_within_window` and the `test_*_cache_key_*` group at lines 297–396, which exercise `mock_cache.add` with the same `(project_id, integrated_agent.uuid, order_id, current_state)` shape). T014a explicitly does NOT replace those tests — it is the Direct Send-specific regression guard that runs alongside them; both cohorts together pin FR-028 across the path-selection branch added by T014.
- [X] T014b [P] [US1] Add a regression test for FR-031 official-agent precedence on the Direct Send cohort in `retail/agents/tests/usecases/test_order_status_agent_resolution_direct_send.py`. With two `IntegratedAgent` fixtures BOTH on `direct_send=True` for the same `Project` — (i) one whose `agent.uuid == settings.ORDER_STATUS_AGENT_UUID` (the official OrderStatus agent), (ii) one whose `parent_agent_uuid` flags it as a custom OrderStatus agent — invoke the order-status webhook entry point with a payload that would match BOTH. Assert: (a) exactly one outbound `flows_service.send_whatsapp_broadcast` call is made (mocked); (b) exactly one `BroadcastMessage` row is persisted; (c) the persisted row's `integrated_agent` FK points at the OFFICIAL fixture (i), NEVER the custom fixture (ii); (d) the audit log contains `[ORDER_STATUS] agent_resolved: vtex_account={...} agent_uuid={official_uuid} source=official` and does NOT contain `source=parent_agent` for this event.

  **Pre-condition (verified at task authoring time)**: the production code at `retail/agents/domains/agent_webhook/usecases/order_status.py:105-109` and `:124-130` already emits the two `[ORDER_STATUS] agent_resolved: vtex_account={...} agent_uuid={...} source={official|parent_agent}` lines documented by FR-039. T014b is therefore a **pure regression pin**, not a code-change task — no production code edit is required for the test to pass on green main. If a future PR moves `_lookup_order_status_agent` and the log line drifts (rename, missing `source=` discriminator, swapped order), T014b will fail; the correct remediation is to **restore the log line shape in production code** (FR-039 makes the shape normative), not to relax the test. Implementers MUST NOT silence T014b by adding/removing fields on the assertion side.

  **Tenant-key note**: the `vtex_account={...}` (rather than `project_uuid={...}`) shape is intentional and spec-compliant per FR-039 (the agent-resolution admission shape is emitted at the entry point alongside the dedup shape, where the project has not yet been resolved) plus FR-044's legacy-preservation rule (existing `vtex_account`-keyed lines stay as-is; `project_uuid` MAY be added additively but is NOT required by this feature). A reviewer who flags the `vtex_account`-only key as a tenant-isolation regression should be referred to FR-044. This pins FR-031 specifically for the Direct Send cohort — without it, a future refactor that re-routed Direct Send-enabled agents through a separate resolution path (e.g. "Direct Send custom agents win") would silently break FR-031 and would not be caught by the existing legacy-cohort tests of `_lookup_order_status_agent`.
- [X] T014c [P] [US1] Add an FR-030 positive-path behavioral test in `retail/agents/tests/usecases/test_order_status_dedup_direct_send.py` (sibling test method on the file authored by T014a). With a Direct Send-enabled `IntegratedAgent` fixture and `@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "test-direct-send-fr030"}})` (Constitution Principle III), invoke `AgentOrderStatusUpdateUsecase.execute(...)` twice with the SAME `(project, integrated_agent.uuid, order_id)` triple but DIFFERENT `current_state` values (e.g. `invoiced` followed by `shipped`). Assert: (a) exactly TWO outbound `flows_service.send_whatsapp_broadcast` calls are made (mocked with `MagicMock(spec=...)`); (b) exactly TWO `BroadcastMessage` rows are persisted, each with the corresponding `current_state`; (c) the two dedup cache keys are DISTINCT — capture them via `unittest.mock.patch("django.core.cache.cache.add", wraps=cache.add)` and assert the two captured `cache_key` arguments are unequal AND that they share the first four `:`-separated segments (project, integrated_agent.uuid, order_id) but differ in the fifth (current_state). This pins FR-030 ("two events differing ONLY in `current_state` MUST both be dispatched as separate logical broadcasts") DIRECTLY for the Direct Send cohort. T014a covers the inverse case (same tuple → 1 dispatch via dedup); T014c covers the difference-in-`current_state` path. Without T014c, FR-030 is only structurally guaranteed by T014a's cache-key-shape assertion (the key includes `current_state` as a component) — which is sound but transitive; T014c makes the behavior assertable directly so a future refactor that collapses the dedup key by dropping `current_state` would fail the test instead of silently merging two distinct logical broadcasts into one.

**Checkpoint**: User Story 1 should be fully functional and testable independently. Dispatch through Direct Send works end-to-end given a pre-existing fixture.

---

## Phase 3.5: Spec correction — `direct_send` storage relocation

These tasks apply retroactively to US1 and are tracked separately so
the original US1 task history stays intact.

> **Task numbering**: T040–T099 are intentionally reserved (unused).
> The jump from T039 to T100 lets future incremental work fit between
> the original task set and the spec-correction phase without
> renumbering existing tasks.

> **Branch-state resolution (pre-pinned 2026-05-21 by `/speckit-analyze`)**:
> Inspection of the live branch `002-direct-send-broadcasts` shows
> NO `direct_send` migration file under `retail/agents/migrations/`
> (latest agents migration is `0025_integratedagent_broadcasts_delivered_and_more.py`)
> and no commit history mentioning a direct_send column on the agents
> app. The `direct_send` field IS present locally on `IntegratedAgent`
> in the working tree (`retail/agents/domains/agent_integration/models.py`,
> unstaged), but `makemigrations` was never run / its output was never
> committed. The branch is unpushed for this change.
> **Therefore T100 takes the "unpushed → no migration file to delete"
> branch — only the model field needs to be removed (T101).** Do NOT
> generate a `RemoveField` migration; there is nothing to remove.

> **Recommended execution order within Phase 3.5 (pinned 2026-05-21 by
> `/speckit-analyze`)**: the safest single-PR order that avoids an
> intermediate broken state is **T100 → T102 → T103 → T104 → T101 →
> T105 → T106**. Specifically: update every read site to
> `obj.config.get("direct_send", False)` (T102) AND every write site to
> `agent.config["direct_send"] = ...` (T103) BEFORE removing the column
> from the model (T101), so no Python execution path ever raises
> `AttributeError` between commits. Migrate the test fixtures (T104) in
> the same window so the test suite stays green at each step. Once
> T101 lands, run T105 / T106 as documented. The alternative order
> (T101 first) is acceptable ONLY if every read/write call site change
> lands atomically in the same commit — the `--dry-run` check on T101
> is robust to either ordering, but a partial commit between T101 and
> T103 would leave a broken working tree.

- [X] T100 Migration handling: the original US1 migration file does
      NOT exist (verified above) and no commit references it. **No
      migration action is required** — proceed directly to T101 to
      drop the field from the model. If a subsequent regeneration
      sequence accidentally creates a `RemoveField` migration during
      T101's `makemigrations` run (because the model field was
      removed from a tree where the column was never materialised in
      Postgres), DELETE that file in-place — it would be a no-op
      migration whose `state_operations` would diverge from the live
      schema.
- [X] T101 Remove `direct_send = models.BooleanField(default=False)`
      from `IntegratedAgent` in
      `retail/agents/domains/agent_integration/models.py`. Run
      `poetry run python manage.py makemigrations agents --dry-run`
      and confirm it reports "No changes detected" (the column was
      never persisted to the schema; if a migration IS proposed,
      discard it per T100). Do NOT run `migrate`.

      **Why "No changes detected" is expected after deleting a model
      field**: Django's migration framework tracks the model state
      recorded by the migration history, NOT the live source. T002
      added the field to the working tree but T003's
      `makemigrations agents --name integratedagent_direct_send`
      output was never committed (see T100's `Branch-state resolution`
      block: "no `direct_send` migration file under
      `retail/agents/migrations/`"). The migration history therefore
      never recorded the field, and removing it from the model
      collapses to a no-op as far as Django is concerned — there is
      nothing to "remove" because there was never anything to "add".
      Surfaced explicitly here so a fresh implementer is not
      surprised by the empty `--dry-run` output.
- [X] T102 Replace `direct_send` field READS with
      `obj.config.get("direct_send", False)` across use cases,
      serializers, and helpers (notably `_resolve_direct_send_flag`,
      `Broadcast.build_message` path selection, and
      `ReadIntegratedAgentSerializer`). Grep
      `rg 'integrated_agent\.direct_send|ia\.direct_send|\.direct_send\s*='`
      to find every call site.
- [X] T103 Replace `direct_send` field WRITES with the **conditional
      JSON-key write** pinned by T026:
      - When the resolved flag is `True`: write
        `agent.config["direct_send"] = True;
        agent.save(update_fields=["config"])`.
      - When the resolved flag is `False` AND no prior key exists in
        `config`: skip the write entirely. Absence is the canonical
        legacy marker per FR-001 / FR-005 / FR-025 / SC-004 / SC-007;
        a write of `False` here would expand the legacy cohort's
        `config` shape and break byte-identical preservation.
      - When the resolved flag is `False` AND a prior `True` exists
        in `config` (re-assignment rollback from Direct Send to
        legacy per `quickstart.md §9`): write
        `agent.config["direct_send"] = False;
        agent.save(update_fields=["config"])` to overwrite — leaving
        `True` would silently route subsequent dispatches through
        the Direct Send path against a legacy channel.

      All write sites MUST stay inside the existing
      `@transaction.atomic` block. The canonical write site is
      `AssignAgentUseCase._create_integrated_agent`; if any other
      site is found (via the grep from T102) the same conditional
      rule applies there. Mirror the one-line code comment from
      T026 at every write site for discoverability.
- [X] T104 Update US1 tests: fixtures must build IntegratedAgents
      with `config={"direct_send": True, ...}` instead of
      `direct_send=True` kwargs; assertions must read from `config`.
      Tests FAIL first (red), then T101–T103 make them green.
      **Affected test files (non-exhaustive — re-grep before edits)**:
      `retail/agents/tests/services/test_broadcast_direct_send.py`,
      `retail/agents/tests/services/test_broadcast_direct_send_persistence.py`,
      `retail/agents/tests/services/test_direct_send_payload_builder.py`,
      `retail/agents/tests/services/test_broadcast.py` (uses
      `self.mock_agent.direct_send = False` at the column-style attribute level),
      `retail/agents/tests/usecases/test_order_status_dedup_direct_send.py`,
      `retail/agents/tests/usecases/test_order_status_agent_resolution_direct_send.py`,
      `retail/agents/tests/usecases/test_assign_direct_send.py` (new in T018),
      `retail/agents/tests/usecases/test_assign_agent.py` (T034),
      `retail/agents/tests/views/test_integrated_agent_viewset.py` (T019).
      **Re-grep recipe** (run before editing to catch any site this
      list misses):
      `rg -n 'integrated_agent\.direct_send|ia\.direct_send|self\.\w+\.direct_send|\.direct_send\s*='`
      across `retail/`. Every match outside `retail/agents/domains/agent_integration/models.py`
      (which T101 deletes) and outside the `_resolve_direct_send_flag`
      / `obj.config.get("direct_send", False)` call sites (which
      already use the JSON-key form) is a fixture or assertion that
      MUST be migrated to `config={"direct_send": True}` build-time
      and `config.get("direct_send", False)` read-time.
      **Task-description sweep**: re-read the descriptions of T011,
      T011a–T011e, T014, T014a, T014b, T018, T018a–T018d, T019, T025,
      T026, T027, T028, T034 — every mention of
      `IntegratedAgent.direct_send=True` as a kwarg / attribute MUST
      be re-interpreted as `config={"direct_send": True}` at fixture
      time and `config.get("direct_send", False)` at read time. The
      task wording itself stays as-is for git-history readability;
      the implementer applies the substitution at code time. T026
      and T027's "plumb the resolved flag" and "Direct Send branch"
      descriptions explicitly call out the JSON-key write pattern.
- [X] T105 Re-run snapshot test T033. The legacy Flows broadcast
      payload MUST remain byte-identical — the whole point of this
      correction.
- [X] T106 Documentation patch — propagate the spec correction to
      operator-facing artefacts so `/speckit-analyze` stops reporting
      `direct_send`-column inconsistencies. Verify (via `rg
      'integratedagent_direct_send|ia\.direct_send|direct_send
      column'`) that the following files have been updated:
      (a) `quickstart.md` §1 (single migration, no agents migration),
      §2 Verification shell (use `ia.config.get("direct_send", False)`),
      §6.1/§6.2 (use `ia.config.get("direct_send", False) == False`),
      §9 Rollback (no "column is additive" sentence; describes the
      JSON-key behaviour);
      (b) `research.md` Decision 1 and Decision 13 (both marked
      "**⚠️ SUPERSEDED by `data-model.md §1`**" headers; original
      reasoning preserved for historical auditability), the §Decision
      11 pseudocode (`integrated_agent.config.get("direct_send",
      False)` instead of `integrated_agent.direct_send`), and the
      "Resolved NEEDS CLARIFICATION items" list (both decisions
      tagged "superseded by `data-model.md §1`");
      (c) **Conditional-write contract** (pinned by T026 / T103):
      verify the implementation of `_create_integrated_agent`
      respects the three-branch rule — write `True` on Direct Send
      assignment, skip the write on new legacy assignment (preserves
      byte-identical `config` shape per FR-001 / FR-005 / FR-025 /
      SC-004 / SC-007), overwrite `True` → `False` on re-assignment
      rollback. Cross-check `T034` against this contract: when
      asserting "Direct Send-DISABLED channel" on a new legacy
      assignment, the assertion MUST be `"direct_send" not in
      ia.config` (key absent), NOT `ia.config["direct_send"] is
      False` (key present). If T034 was authored against the
      column-style attribute (`ia.direct_send == False`), the
      substitution from T104 yields the absence-of-key form
      automatically.
      All edits already applied at T106 authoring time
      (`/speckit-analyze` remediation, 2026-05-21); this task is the
      verification gate — if a future PR introduces a new
      column-style reference OR an unconditional
      `config["direct_send"] = False` write on the legacy path,
      this task fails and a follow-up patch is required before
      merge.

**Checkpoint**: Live model + tests are aligned with `data-model.md §1` (`direct_send` lives inside `IntegratedAgent.config` JSON; no model column). Phase 4 (US2) can now be authored against the canonical storage shape from the start.

---

## Phase 4: User Story 2 — Onboard an OrderStatus agent without creating templates in Meta (Priority: P2)

**Goal**: When the operator assigns the OrderStatus agent to a project whose WhatsApp channel reports Direct Send enabled, persist all OrderStatus templates locally with content fetched from Meta's library catalog (in the project's resolved language, with per-template `pt_BR` fallback), set `IntegratedAgent.direct_send=True`, and skip every Meta / Integrations template-creation submission. The whole flow stays inside the existing `@transaction.atomic` and fails atomically if any required template is unavailable in both languages.

**Independent Test**: Configure a project whose `App.config.direct_send=True` (mocked at `IntegrationsService.get_channel_app`) and assign the OrderStatus agent. Verify zero calls to `notify_integrations` / `IntegrationsService.fetch_templates_from_user`, every persisted Template carries body/header/footer/buttons in the project's language (or `pt_BR` with a logged warning per fallback), every Version is `status="APPROVED"`, and `IntegratedAgent.direct_send=True`.

### Tests for User Story 2 (TDD — write FIRST, ensure FAIL before implementation)

- [X] T015 [P] [US2] Tests for `MetaClient.fetch_library_template_by_name_and_language` in `retail/clients/meta/tests/test_meta_client.py` covering: HTTP success returns the exact-name + exact-language match when Meta returns multiple fuzzy hits (contracts/meta-library-catalog.md §3); HTTP success with no exact-name match returns `None`; HTTP success with an exact-name match but a different `language` field — the cross-language false-positive scenario (Meta returns the `pt_BR` variant of the template when `es_MX` was requested but missing) — returns `None` so the use case can correctly trigger the `pt_BR` fallback path; HTTP success with empty `data` returns `None`; HTTP success with a response item that omits the `language` field is accepted as a name-match (contract §3 makes the language guard conditional on the field's presence); HTTP failure (mock `make_request` to raise `CustomAPIException`) propagates the exception (the service layer is responsible for swallowing it).
- [X] T016 [P] [US2] Tests for `MetaService.fetch_library_template_by_name_and_language` in `retail/services/meta/tests/test_meta_service.py` covering: passthrough on client success; returns `None` on `CustomAPIException` with an `error` log including `template_name` and `language`; returns `None` and logs `error` when the client returns a payload whose shape `TemplateTranslationAdapter` rejects (mock the adapter to raise; matches `contracts/meta-library-catalog.md §4` "malformed JSON / unexpected schema" failure mode).
- [X] T017 [P] [US2] Tests for `_meta_library_template_fetch.py` helpers in `retail/templates/tests/usecases/test_meta_library_template_fetch.py`:
  - For the pure adapter `adapt_meta_library_template_response` (T023(a)): returns the local-`Template.metadata` shape (`header`/`body`/`body_params`/`footer`/`buttons`/`category`/`language`) for a typical OrderStatus template; returns `None` when `raw is None`; raises `DirectSendUnsupportedComponentError` when the raw response carries (i) an unsupported component type (e.g. carousel, list, catalog, order_details, flow message), (ii) more than one `URL` button or more than three `QUICK_REPLY` buttons, (iii) any pre-substitution component exceeding Meta's documented length limits — body > 1024, header.text > 60, footer > 60, button text > 20 chars, or (iv) a malformed / missing-key payload that the adapter cannot decode (`contracts/meta-library-catalog.md §4` — "malformed JSON / unexpected schema").
  - For the Direct-Send-only wrapper `fetch_meta_library_template_metadata` (T023(b)): returns the adapter output on service success; returns `None` when the service returns `None`; propagates `DirectSendUnsupportedComponentError` raised by the adapter (`contracts/meta-library-catalog.md §5`; research Decision 12).
- [X] T018 [P] [US2] **`_resolve_direct_send_flag` paths** — Tests for `AssignAgentUseCase._resolve_direct_send_flag` in `retail/agents/tests/usecases/test_assign_direct_send.py` covering: (a) returns `True` when `IntegrationsService.get_channel_app` reports `config.direct_send=True`; (b) returns `False` with a WARNING log `[DirectSend] channel_lookup_failed: agent={...} app_uuid={...}` when `IntegrationsService.get_channel_app` returns `None`; (c) returns `False` with no warning when the channel returns `200` but `config.direct_send` is missing or `False`; (d) returns `False` for non-OrderStatus agents regardless of the channel flag (FR-019). Use `MagicMock(spec=IntegrationsService)` to inject the service per Constitution Principle III.
- [X] T018a [P] [US2] **Happy path (Story 2 AS1)** — Test in the same file (`test_assign_direct_send.py`) covering Story 2 AS1: an end-to-end `AssignAgentUseCase.execute(...)` against a Direct Send-enabled channel persists `Template`+`Version` with `version.status="APPROVED"`, `metadata.direct_send` sub-object populated (`fetched_from_meta_library`, `fetched_at`, `requested_language`, `actual_language`), `IntegratedAgent.direct_send=True`, ZERO calls to `notify_integrations` / `IntegrationsService.fetch_templates_from_user` / `IntegrationsService.create_template_message` / `IntegrationsService.create_library_template_message` (SC-003). One INFO log `[DirectSend] template_persisted: project_uuid={...} agent={...} template={...} requested_language={...} actual_language={...}` is emitted per persisted Template (captured with `assertLogs` at INFO level — FR-039 mandates `project_uuid` as a top-level key; referenced by `quickstart.md §2`).
- [X] T018b [P] [US2] **`pt_BR` per-template fallback (Story 2 AS4)** — Test in the same file covering Story 2 AS4 / FR-003c: configure `MetaService.fetch_library_template_by_name_and_language` to return content for SOME templates in the project locale and `None` for OTHERS (forcing those to fall back to `pt_BR`). Assert: the missing-locale templates are persisted with `pt_BR` content; the `pt_BR`-falling-back templates emit the WARNING log `[DirectSend] template_language_fallback: project_uuid={...} agent={...} template={...} requested_language={...} fallback_language=pt_BR` (captured with `assertLogs` at WARNING level — one entry per fallback); `IntegratedAgent.direct_send=True`; mixed-language assignment succeeds atomically (all rows persisted, none rolled back).
- [X] T018c [P] [US2] **Atomic rollback — both languages fail (Story 2 AS5 / FR-003d)** — Test in the same file covering Story 2 AS5: configure `MetaService.fetch_library_template_by_name_and_language` to return `None` for BOTH the project locale and `pt_BR` for at least one required template. Assert: `DirectSendTemplateUnavailableError` is raised; `transaction.atomic` rolls back; `IntegratedAgent.objects.count()`, `Template.objects.count()`, `Version.objects.count()`, and `Credential.objects.count()` are ALL unchanged from their pre-`execute` baseline (zero rows of any kind persist); the ERROR log line `[DirectSend] assignment_failed_atomic: project_uuid={...} agent={...} template={...} requested_language={...} fallback_language=pt_BR reason={missing_translation|meta_unreachable|malformed_response}` is emitted exactly once before the rollback (captured with `assertLogs` at ERROR level — FR-039 mandates `project_uuid` as a top-level key).
- [X] T018d [P] [US2] **Atomic rollback — unsupported component (Decision 12)** — Test in the same file covering Decision 12: configure `MetaService.fetch_library_template_by_name_and_language` to return a template whose components are outside the Direct Send Beta supported set (e.g. carousel) so `adapt_meta_library_template_response` raises `DirectSendUnsupportedComponentError`. Assert: `transaction.atomic` rolls back with the SAME explicit row-by-row assertions as T018c: `IntegratedAgent.objects.count()`, `Template.objects.count()`, `Version.objects.count()`, and `Credential.objects.count()` are all unchanged from the pre-execute baseline; the DRF response body carries `code="direct_send_unsupported_component"` with HTTP 422 (per T007's `default_code` contract).
- [X] T018e [P] [US2] **Re-assignment after `is_active=False` re-fetches every template (spec Edge Case "Re-assignment of an OrderStatus agent after a previous assignment was marked `is_active=False`")** — Test in the same file (`test_assign_direct_send.py`) covering the spec's "snapshot at assignment time" guarantee across the re-assignment surface. Seed a pre-existing `IntegratedAgent` row (project A, OrderStatus agent) with `is_active=False`, plus a previously-persisted `Template`+`Version` set FK-linked to that inactive row whose `metadata.direct_send.actual_language="pt_BR"` (i.e. the prior assignment fell back). Then call `AssignAgentUseCase.execute(...)` against the SAME `(project, agent)` pair on a Direct Send-enabled channel whose project locale resolves to `es_MX`. Assert: (a) `MetaService.fetch_library_template_by_name_and_language(...)` is invoked exactly N times with `language="es_MX"` (where N = the OrderStatus agent's pre-approved template count), proving no partial-batch or per-template result from the previous assignment was reused (FR-003a, FR-003d last sentence — "no partial-batch results are cached between attempts"); (b) a NEW `IntegratedAgent` row is persisted with `is_active=True` and the resolved Direct Send flag, leaving the prior `is_active=False` row untouched (`IntegratedAgent.objects.filter(is_active=False).count()` is unchanged after `execute`); (c) the previously-persisted `Template` / `Version` rows from the inactive IntegratedAgent are NOT reassigned, renamed, or repointed — assert their FKs still point at the original inactive `IntegratedAgent` row (`Template.objects.filter(integrated_agent_id=inactive_ia.id).count()` is unchanged); (d) the newly-persisted Templates carry fresh `metadata.direct_send` sub-objects whose `actual_language` matches the re-fetched language (e.g. `es_MX` when the second-attempt fetch succeeds without fallback), proving the snapshot is captured anew per FR-003a–FR-003c. Use `MagicMock(spec=MetaService)` to control per-call return values per Constitution Principle III.
- [X] T019 [P] [US2] Tests for `ReadIntegratedAgentSerializer` exposing `direct_send` (read-only) in `retail/agents/tests/views/test_integrated_agent_viewset.py` (or its serializer test if it exists): serialized output of an IntegratedAgent with `direct_send=True` includes `"direct_send": true`; with `direct_send=False` includes `"direct_send": false`.

### Implementation for User Story 2

- [X] T020 [P] [US2] Extend `MetaClientInterface` Protocol in `retail/interfaces/clients/meta/client.py` with `fetch_library_template_by_name_and_language(template_name: str, language: str) -> Optional[Dict[str, Any]]`. Extend `MetaServiceInterface` Protocol in `retail/interfaces/services/meta.py` with the same method signature.
- [X] T021 [US2] Implement `MetaClient.fetch_library_template_by_name_and_language` in `retail/clients/meta/client.py`: same auth headers and base URL as the existing `get_pre_approved_template`; calls `GET {self.url}/message_template_library/?search={template_name}&language={language}`; iterates `response["data"]` and returns the first item whose `name == template_name` (case-sensitive) AND, when the item carries a `language` field, whose `language == language` (case-sensitive on the locale string — this guards against Meta's fuzzy-search returning a `pt_BR` variant when an `es_MX` translation was requested but missing, per contract §3); items without a `language` field fall through the language guard and are matched on name alone; returns `None` when no item satisfies both filters (contracts/meta-library-catalog.md §1–§3).
- [X] T022 [US2] Implement `MetaService.fetch_library_template_by_name_and_language` in `retail/services/meta/service.py`: wraps the client, catches `CustomAPIException`, logs `error` with `template_name` and `language`, returns `None` on failure (contracts/meta-library-catalog.md §4; Constitution Principle I — Service contract).
- [X] T023 [US2] Add TWO helpers in `retail/templates/usecases/_meta_library_template_fetch.py` per research Decision 9:
  - (a) `adapt_meta_library_template_response(raw: Optional[Dict[str, Any]]) -> Optional[TemplateInfo]` — pure adapter. Returns `None` when `raw is None`; otherwise runs the response through the existing `TemplateTranslationAdapter`, validates components against the Direct Send Beta supported set per `contracts/meta-library-catalog.md` §5 (body required and non-empty; header type ∈ {TEXT, IMAGE} or absent; buttons type ∈ {URL, QUICK_REPLY} or absent; ≤1 URL button; ≤3 QUICK_REPLY buttons; pre-substitution length limits — body ≤ `MAX_BODY_LENGTH`, header.text ≤ `MAX_HEADER_TEXT_LENGTH`, footer ≤ `MAX_FOOTER_LENGTH`, button `display_text` (cta_url) ≤ `MAX_BUTTON_LABEL_LENGTH`, button `title` (reply) ≤ `MAX_BUTTON_LABEL_LENGTH`; button `url` is NOT length-checked here per `contracts/messaging-gateway-payload.md` §3.3 — constants imported from `retail/agents/domains/agent_webhook/services/direct_send_constants.py` (T007a)). Raises `DirectSendUnsupportedComponentError` on any violation with `component_type` describing the violation. Used by BOTH the legacy push-time validation (via T024) and the Direct Send branch (via wrapper (b)).
  - (b) `fetch_meta_library_template_metadata(meta_service, template_name: str, language: str) -> Optional[TemplateInfo]` — Direct-Send-only HTTP fetcher. Calls `meta_service.fetch_library_template_by_name_and_language(name, language)` (the new exact-match method from T022) and delegates the response to T023(a). Returns `None` when the service returns `None`.

  The split preserves Decision 4's "push-time keeps fuzzy semantics" guarantee while extracting the response-shaping drift risk per Decision 9.
- [X] T024 [US2] Refactor `ValidatePreApprovedTemplatesUseCase._get_template_info` in `retail/agents/domains/agent_management/usecases/validate_templates.py` to keep calling `meta_service.get_pre_approved_template(name, language)` (fuzzy semantics preserved per research Decision 4) and delegate ONLY the response-shaping step to `adapt_meta_library_template_response` from T023(a). Behavior must remain identical for the legacy push-time validation — same HTTP call, same first-hit selection, same `TemplateInfo` output shape; existing tests of `_get_template_info` must keep passing without modification (research Decision 9). **⚠️ Test deviation**: existing `test_validate_pre_approved_templates.py` was updated minimally — the `template_adapter` constructor kwarg was removed (the adapter is now encapsulated in `_meta_library_template_fetch.py`) and the `metadata.header` assertion changed from `{"type": "TEXT", "text": "..."}` (mocked legacy transformer return) to `{"header_type": "TEXT", "text": "..."}` (the canonical Retail-internal shape consumed by `Broadcast.build_broadcast_template_message` at `broadcast.py:100` `header["header_type"]` AND by `Broadcast.build_direct_send_message`). The legacy code's mocked-only path was producing the wrong key (`type` vs `header_type`); this is a latent-bug fix, not a behavior regression — see `data-model.md §3` for the canonical metadata shape.
- [X] T025 [US2] Implement `AssignAgentUseCase._resolve_direct_send_flag(agent: Agent, app_uuid: UUID) -> bool` in `retail/agents/domains/agent_integration/usecases/assign.py`: returns `False` when `str(agent.uuid) != settings.ORDER_STATUS_AGENT_UUID` (FR-019); otherwise calls `self.integrations_service.get_channel_app("wpp-cloud", str(app_uuid))`; on `None` logs `[DirectSend] channel_lookup_failed: agent={agent.uuid} app_uuid={app_uuid}` and returns `False`; otherwise returns `bool((app.get("config") or {}).get("direct_send", False))` (contracts/integrations-channel-app.md §4).
- [X] T026 [US2] Plumb the resolved `direct_send` flag through `AssignAgentUseCase.execute` and `_create_integrated_agent` in `retail/agents/domains/agent_integration/usecases/assign.py`: `execute` calls `_resolve_direct_send_flag` once before `_create_integrated_agent` and passes it as a kwarg. Per `data-model.md §1` (post-correction) the write semantic is **conditional** — `direct_send` is an "optional key" (FR-001) whose absence is canonically interpreted as `False` (FR-005, FR-025; quickstart §6.1 / §6.2), so the persisted `config` shape on the legacy cohort MUST stay byte-identical to the pre-feature shape (SC-004, SC-007):
  - **Direct Send-path new assignment** (`direct_send is True`): write `agent.config["direct_send"] = True` — either by including it in `_create_integrated_agent`'s `defaults` / row-creation dict, or via a post-create `agent.config["direct_send"] = True; agent.save(update_fields=["config"])` inside the existing `@transaction.atomic` block.
  - **Legacy-path new assignment** (`direct_send is False` AND no prior key exists in the existing `config`): do NOT write the key. Absence is the canonical legacy marker — writing `False` would expand the legacy cohort's `config` JSON shape by one key per assignment and silently break the byte-identical preservation rule.
  - **Re-assignment that flips from `True` to `False`** (operator-initiated rollback path documented in `quickstart.md §9`): write `agent.config["direct_send"] = False` to overwrite the prior `True`. The key MUST NOT be left at `True` after a legacy-path re-assignment because subsequent dispatches read `config.get("direct_send", False)` and would silently take the Direct Send path against a legacy channel.

  Do NOT write to a top-level `direct_send` column (the field does not exist on the model after T101). Add a defensive one-line code comment immediately above the conditional write so the implicit invariant is discoverable from the code itself, e.g. `# FR-001 / SC-004: write the key only when True or when overwriting a prior True; absence is the canonical legacy marker.`
- [X] T027 [US2] Add the Direct Send branch in `AssignAgentUseCase._create_library_templates` in `retail/agents/domains/agent_integration/usecases/assign.py`: when `integrated_agent.direct_send` is `True`, for every `pre_approved` resolve `project_language = integrated_agent.config.get("initial_template_language", DEFAULT_TEMPLATE_LANGUAGE)` (the same key already populated from the VTEX tenant locale by `AssignAgentUseCase._build_initial_config` at `retail/agents/domains/agent_integration/usecases/assign.py:122-169`, satisfying FR-003b); call the Direct-Send fetch wrapper `fetch_meta_library_template_metadata` (T023(b)) with `project_language`, then with `"pt_BR"` if the first call returned `None` and `project_language != "pt_BR"`, logging a WARNING `[DirectSend] template_language_fallback: project_uuid={project.uuid} agent={...} template={...} requested_language={project_language} fallback_language=pt_BR` on the second call's success (FR-003c); raise `DirectSendTemplateUnavailableError` when both calls return `None` (FR-003d) — emit an ERROR log `[DirectSend] assignment_failed_atomic: project_uuid={project.uuid} agent={...} template={...} requested_language={project_language} fallback_language=pt_BR reason={...}` immediately before raising so the atomic rollback is observable in logs (FR-039 mandates `project_uuid` as a top-level key; referenced by `quickstart.md §7`); persist a local `Template` + `Version` with the helper's metadata, `version.status = "APPROVED"`, `version.template_name = pre_approved.name`, `version.integrations_app_uuid = app_uuid`, `template.metadata` carrying the fetched content + the `direct_send` observability sub-object (`fetched_from_meta_library`, `fetched_at`, `requested_language`, `actual_language`); after each successful persist emit an INFO log `[DirectSend] template_persisted: project_uuid={project.uuid} agent={...} template={...} requested_language={project_language} actual_language={actual_language}` (referenced by `quickstart.md §2`); skip every `notify_integrations` / `fetch_templates_from_user` call on this branch (research Decision 5; data-model.md §3 / §4). Reuse the existing `TemplateBuilderMixin.build_template_and_version` for the persistence step to stay consistent with `_adopt_customer_templates`.
- [X] T028 [US2] Expose `direct_send` (read-only) on `ReadIntegratedAgentSerializer` in `retail/agents/domains/agent_integration/serializers.py` (data-model.md §9 last row).

**Checkpoint**: User Stories 1 AND 2 should both work independently. An end-to-end run of the assignment + dispatch path now succeeds against a Direct Send-enabled channel without any Meta/Integrations template-creation traffic.

---

## Phase 5: User Story 3 — Block broadcasts for paused or flagged templates (Priority: P3)

**Goal**: When the rule engine names a template whose current version is `PAUSED` or `FLAGGED`, dispatch is skipped silently, no Flows call is made, no `BroadcastMessage` row is persisted, and an audit log entry records the skip. When the version returns to `APPROVED`, broadcasts resume on the next webhook.

**Independent Test**: Use a Direct Send-enabled OrderStatus IntegratedAgent fixture with one `Template` whose `current_version.status="PAUSED"`. Call `Broadcast.build_message(integrated_agent, {"template": "<name>", ...})` and assert (a) it returns `None`, (b) Flows is NOT called, (c) `BroadcastMessage` is NOT persisted, (d) a WARNING log entry includes the template name, the version status `PAUSED`, and the order-status event identifier. Repeat with `FLAGGED`. Then flip the version back to `APPROVED` and assert dispatch proceeds normally.

### Tests for User Story 3 (TDD — write FIRST, ensure FAIL before implementation)

- [X] T029 [P] [US3] Tests for `Broadcast.get_current_template` in `retail/agents/tests/services/test_broadcast.py` covering: Story 3 AS1 — `current_version.status="PAUSED"` → returns `None` AND emits a WARNING audit log whose message satisfies ALL of the following (matching the literal format pinned by T031 + FR-039's unified Dispatch-gate skip shape): (i) starts with the literal prefix `[BroadcastDispatch] skipped_due_to_status:`; (ii) contains the substring `project_uuid={integrated_agent.project.uuid}` as a TOP-LEVEL key (assert with `assertIn(f"project_uuid={ia.project.uuid}", record.getMessage())` — this directly verifies FR-039 + FR-044's "MUST carry the project identifier as a top-level structured field" rule, which a plain "matching the format pinned by T031" cross-reference cannot enforce at unit-test level); (iii) contains `vtex_account={integrated_agent.project.vtex_account}` as a TOP-LEVEL key (FR-044 — both `project_uuid` and `vtex_account` are top-level structured fields on the unified shape so operators can filter by either tenant identifier); (iv) contains `template={template.name}`; (v) contains `version_status=PAUSED`; (vi) contains the originating order-status event payload data (FR-012); Story 3 AS2 — same six-part assertion for `"FLAGGED"` (only `version_status=FLAGGED` differs); Story 3 AS3 / SC-006 — after flipping the version's status back to `"APPROVED"` the next call returns the Template (regression test, no audit log emitted); **Unified-shape regression** — pre-existing non-APPROVED states (`PENDING`, `REJECTED`, `IN_APPEAL`, `LOCKED`, `DISABLED`, `DELETED`, `PENDING_DELETION`) emit the SAME unified audit shape with `version_status={state}` (per FR-027 Exception clause + FR-039 unified entry — the historical "Template not found ..." per-name miss line at `get_current_template` has been consolidated into this shape; the downstream `Broadcast.build_message` "Template not found or has no approved current version" line is unchanged and still fires per FR-039 "Legacy downstream miss"); **NOT_FOUND case** — when no `Template` row matches the requested name (`template is None` after the filter), `get_current_template` emits the unified audit shape with `version_status=NOT_FOUND` (FR-027 Exception clause); concurrency edge case — two sequential `get_current_template` calls against the same `PAUSED` template both return `None` and both emit the audit log entry (proves the gate is per-event and stateless, satisfying spec edge case "concurrent broadcasts targeting the same paused template").
- [X] T030 [P] [US3] Tests for `SendTestTemplateUseCase._get_active_template` in `retail/api/integrated_agent/tests/test_send_test_template.py` covering: `current_version.status="PAUSED"` → `ValidationError` whose `detail` includes the literal `"PAUSED"` so QA users can see the cause; same for `"FLAGGED"`; pre-existing non-APPROVED states keep their current error message unchanged.
- [X] T030a [P] [US3] Tests for `UpdateTemplateUseCase` in `retail/templates/tests/usecases/test_update_template.py` covering FR-026: posting `status="PAUSED"` to the named `Version` persists the new status as-is; the template's `current_version` FK is unchanged (the APPROVED-only promotion logic does NOT fire); same for `status="FLAGGED"`; existing `status="APPROVED"` behavior (current_version promotion) is unchanged; existing `status="PENDING"` / `"REJECTED"` behavior is unchanged. This pins FR-026's "accept and persist as-is, do NOT promote" contract. The test relies on two invariants of the existing implementation: (a) T006 extends the `UpdateTemplateData` `Literal` (a static type hint only); (b) `UpdateTemplateUseCase.execute` at `retail/templates/usecases/update_template.py:44-58` reads `payload.get("status")` directly and writes it to `version.status` without any runtime enum/choices validation — the use case's only branch is `if status == "APPROVED"` which falls through for `PAUSED`/`FLAGGED`, and Django's model-level `STATUS_CHOICES` validation now accepts the two new values after T004. The test exercises an end-to-end `execute({"status": "PAUSED", "version_uuid": ...})` and asserts `version.status == "PAUSED"` plus `template.current_version` unchanged — proving the input flows through unmodified. **Additionally**, add a defensive one-line code comment immediately above the `if status == "APPROVED":` branch in `UpdateTemplateUseCase.execute` so the implicit invariant (b) is discoverable from the code itself: `# FR-026: PAUSED/FLAGGED persisted as-is; do NOT add full_clean()/choices validation here — it would re-validate against historical choices and silently break dispatch-time gating.` Without this comment, a future PR adding defensive validation could break FR-026 without triggering any test failure (the test asserts current behavior, not the absence of `full_clean()`).

### Implementation for User Story 3

- [X] T031 [US3] Tighten `Broadcast.get_current_template` in `retail/agents/domains/agent_webhook/services/broadcast.py:602`. **Strategy choice (implementation-only)**: replace the original `.filter(..., current_version__status="APPROVED").first()` with a **single** `.filter(name=..., is_active=True, current_version__isnull=False).select_related("current_version").first()` query and classify the version status in Python — `APPROVED` returns the Template; **every other outcome** (including `template is None`) routes through the unified `_log_dispatch_skipped_due_to_status` helper, which emits a single WARNING audit line `[BroadcastDispatch] skipped_due_to_status: project_uuid={integrated_agent.project.uuid} vtex_account={integrated_agent.project.vtex_account} agent={...} template={...} version_status={NOT_FOUND|PAUSED|FLAGGED|<other status>} event={data}` and returns `None` (research Decision 10; FR-012; FR-027 Exception clause; FR-039 mandates `project_uuid` AND `vtex_account` as top-level keys per FR-044). The `version_status` discriminator carries the skip class — `NOT_FOUND` when no row matched, the actual `Version.status` otherwise — so log consumers can route on each class independently without parser changes. The legacy `WARNING "Template not found or has no approved version"` per-name miss line previously emitted by this method is REMOVED by this consolidation (FR-027 Exception clause); the downstream `Broadcast.build_message` "Template not found or has no approved current version" line is UNTOUCHED and continues to fire when `get_current_template` returns `None` (FR-039 "Legacy downstream miss"). Pinned by `test_get_current_template_issues_single_filter_call` so a regression that re-introduces a sibling fallback query fails the test even on the happy path.
- [X] T032 [US3] Update `SendTestTemplateUseCase._get_active_template` in `retail/api/integrated_agent/usecases/send_test_template.py:50`. **Strategy choice (implementation-only, observable behavior identical to a sibling-lookup approach)**: replace the original `.filter(..., current_version__status="APPROVED").first()` with a **single** `.filter(is_active=True, current_version__isnull=False).select_related("current_version").first()` query and classify the version status in Python — `APPROVED` returns the Template; `PAUSED`/`FLAGGED` raises `ValidationError` whose `detail` includes the status reason (e.g. `"Template version is PAUSED and cannot be dispatched."`); any other status (or no row) keeps the current `"No active approved template found …"` message. Pinned by `test_get_active_template_issues_single_filter_call` so a regression that re-introduces a sibling fallback query fails the test even on the happy path.

**Checkpoint**: All three user stories work independently. Dispatch is correctly blocked for `PAUSED`/`FLAGGED` and resumes when the status returns to `APPROVED`.

---

## Phase 6: User Story 4 — Existing OrderStatus agents continue to broadcast unchanged (Priority: P4)

**Goal**: The legacy dispatch path is byte-identical with today for any IntegratedAgent whose `direct_send=False` (the default for every existing row plus every new assignment against a non-Direct-Send channel). FR-015, SC-004 — zero regression.

**Independent Test**: Replay a fixture VTEX order-status webhook against a Direct Send-DISABLED IntegratedAgent. Assert the JSON sent to Flows is byte-identical with a snapshot captured before the feature was introduced. Repeat against an IntegratedAgent created through the legacy assignment branch and verify the existing `notify_integrations` / `fetch_templates_from_user` calls fire exactly as today.

### Tests for User Story 4 (TDD — write FIRST, ensure FAIL before implementation; no implementation tasks needed)

- [X] T033 [P] [US4] Snapshot tests for the legacy payload in `retail/agents/tests/services/test_broadcast_legacy_payload.py` covering Story 4 AS1: assert `Broadcast.build_broadcast_template_message` emits the EXACT byte-shape used today for: (a) body + positional variables (no header, no buttons, no attachments); (b) body + image header (s3-keyed) + `url`-sub_type button + variables; (c) body + image header (direct URL) + `payment_request`-sub_type buttons + `interaction_type=order_details` + `order_details` payload. Each scenario pins a fixture JSON file under the same `tests/services/__snapshots__/` (or inline) so any drift fails the test.
- [X] T034 [P] [US4] Tests for the legacy assignment branch in `retail/agents/tests/usecases/test_assign_agent.py` covering: Story 2 AS2 — Direct Send-DISABLED channel persists `IntegratedAgent.direct_send=False`, AND `_create_library_templates` still calls `CreateLibraryTemplateUseCase.execute` + `notify_integrations` AND `_adopt_customer_templates` still calls `IntegrationsService.fetch_templates_from_user` exactly as today (zero new calls, zero removed calls, same arguments). **⚠️ Post-Phase 3.5 assertion substitution** (T104 / T106): the task description above keeps the column-style wording for git-history readability, but on a fresh checkout the assertion MUST be `self.assertNotIn("direct_send", ia.config)` (key absent) instead of `self.assertFalse(ia.direct_send)` (column read). Writing `False` unconditionally on a new legacy assignment expands the `config` JSON shape by one key per assignment and silently breaks FR-001 / FR-005 / SC-004 / SC-007's byte-identical preservation rule — see T026's conditional-write contract for the canonical persistence shape.
- [X] T035 [P] [US4] Test for Story 4 AS2 in `retail/agents/tests/services/test_broadcast.py`: a Direct Send-DISABLED IntegratedAgent with a `Template` whose `current_version.status` is `PENDING` / `REJECTED` / etc. (any pre-existing non-APPROVED state) still produces a SKIPPED dispatch — `Broadcast.build_message` returns `None`, no Flows call is made, no `BroadcastMessage` row is persisted. The audit log shape is the **unified** `[BroadcastDispatch] skipped_due_to_status: ... version_status={state}` line emitted by `get_current_template` per FR-027 Exception clause + FR-039 "Dispatch-gate skip (unified shape)" (the same shape emitted on the Direct Send cohort — the gate is path-independent and applies identically to both cohorts per FR-008 + FR-046). The downstream "Template not found or has no approved current version" line emitted by `build_message` after `get_current_template` returns `None` continues to fire UNCHANGED on this path per FR-039 "Legacy downstream miss" + FR-027.
- [X] T035a [P] [US4] Snapshot tests for the legacy datalake event payload in `retail/agents/tests/services/test_broadcast_legacy_datalake.py` covering FR-020 / SC-008: assert the `weni_datalake_sdk` and `CommerceWebhookPath` events emitted by the legacy dispatch path have the same set of keys, value types, and emission count as a baseline fixture captured before the feature. Pin one snapshot per template family covered by T033 (body-only, image-header-with-CTA-URL, image-header-with-payment-buttons-plus-`order_details`) so any drift in the datalake schema fails CI. Mock the SDK at the boundary with `unittest.mock.patch` to capture the exact `send(...)` calls without hitting real infra (Constitution Principle III).
- [X] T035b [P] [US4] Snapshot test for legacy Sentry / Elastic APM dispatch span tags in `retail/agents/tests/services/test_broadcast_legacy_observability.py` covering FR-027 / SC-008: capture the tag set emitted by `Broadcast.send_message` against a Direct Send-DISABLED fixture and assert (a) no existing tag key is renamed or removed against the pre-feature baseline, (b) the optional `direct_send` tag is absent (or `False`) on this path. Use `unittest.mock.patch` on the Sentry / APM SDK boundary to capture the tags without sending to a real backend.
- [X] T035c [P] [US1, US4] Tenant-isolation regression guard in `retail/agents/tests/services/test_broadcast_tenant_isolation.py` covering FR-040 / SC-010 (a): seed two `Project` rows (project A, project B) each with their own `IntegratedAgent`, dispatch one Direct Send broadcast in project A and one legacy broadcast in project B, then assert the SQL invariant `BroadcastMessage.project_id == BroadcastMessage.integrated_agent.project_id` holds for every persisted row across both projects. The test MUST also confirm that (i) the dedup cache key for project A's broadcast carries `project_id=A` and never `B`, (ii) the datalake event payload carries `project=str(A.uuid)` and never `B.uuid` (FR-042), and (iii) the per-IntegratedAgent template lookup `integrated_agent.templates.filter(name=...)` returns only the IntegratedAgent's own templates even when both projects' Templates share the same `name` (FR-045). Mock the SDK / cache at the boundary with `@override_settings(CACHES={...LocMemCache...})` (Constitution Principle III). This test is the materialized form of the SC-010 (a) audit query and a regression here is a hard tenant-isolation failure.

**Checkpoint**: All four user stories work independently. The legacy regression guard pins the byte-shape of every existing wire payload, the datalake event keys, and the observability span tags; any future drift fails the snapshot tests. The tenant-isolation regression guard (T035c) materializes the SC-010 (a) audit query as a CI-runnable assertion.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validate the feature end-to-end and confirm coverage / formatting parity.

- [X] T036 [P] Run the `quickstart.md` validation script step-by-step in a local environment with a Direct Send-enabled fixture (see `quickstart.md §0 Prerequisites` for the fixture composition — OrderStatus agent pushed, WhatsApp Cloud channel created via onboarding, channel opted into Direct Send Beta with `App.config.direct_send=True`, project's VTEX tenant has a resolvable `defaultLocale`, `settings.ORDER_STATUS_AGENT_UUID` set, Meta library catalog has the OrderStatus templates available in the project's locale or `pt_BR`) and confirm every "Expected outcome" matches.
- [X] T037 Run `poetry run coverage run manage.py test && poetry run coverage report -m | tee /tmp/feature_coverage.txt` and then `poetry run python contrib/compare_coverage.py`. The compare script MUST NOT report `Number of test lines decreased`; if it does, add the missing tests in the same PR (Constitution Principle III — NON-NEGOTIABLE).
- [X] T038 [P] Run pre-commit on every changed file: `poetry run pre-commit run --files <changed-files>`. Black + flake8 must pass clean.
- [X] T039 Open the PR with title `feat: add WhatsApp Direct Send dispatch path for OrderStatus` (≤72 chars) and a body following the `## What` / `## Why` template (Constitution Principle V). Branch name: `002-direct-send-broadcasts` (already provided by `/speckit-plan`). Reference the spec, plan and research files in the body. The PR body MUST also include a **`## Backward-compatibility & untestable-by-design checklist gate`** section that explicitly confirms the SIX requirements `plan.md` §Complexity Tracking documents as having no automated test — three "thou shalt not" backward-compat requirements (FR-022 / FR-023 / FR-024), the Celery one-shot stance (FR-038), the inbound EDA tenant-resolution restatement (FR-041), and the FR-043 v1 deferral — were reviewed against `checklists/backward-compatibility.md` (CHK013–CHK022, CHK027–CHK029), `checklists/idempotency.md` (CHK014), and `checklists/tenant-isolation.md` (CHK022–CHK025, CHK044) and remain satisfied: (i) FR-022 — no required field was added to any inbound payload (order-status webhook, agent-assignment, send-test-template, template-status webhook); no URL path, HTTP method, required header, or required query parameter was renamed or removed; (ii) FR-023 — the template-status webhook handler is untouched (no new Integrations Engine subscription, no signature change, no downstream side-effect change); (iii) FR-024 — no new environment variable or settings key was introduced (deploying the feature without any settings change is safe); (iv) FR-038 — `retail/celery.py` diff is empty for retry-related keys (no `task_acks_late=True` override, no `task_default_retry_delay` change, no broker DLX configuration added) AND the three OrderStatus-pipeline tasks (`task_order_status_update`, `task_mark_broadcast_converted`, `handle_purchase_event_task`) carry no new `bind=True` / `retry_kwargs={...}` decorators / `self.retry(...)` calls; (v) FR-041 — no inbound EDA consumer (`BroadcastSendConsumer` on `retail.template-send`, `BroadcastStatusConsumer` on `retail.template-status`, the order-status webhook entry point at `retail/agents/domains/agent_webhook/usecases/order_status.py`) was modified by this PR; tenant-resolution mechanisms (a)–(d) remain unchanged and are covered transitively by T035c; (vi) FR-043 — the explicit Retail-side cross-validation (`app.config.project_uuid == request.headers["Project-Uuid"]` with HTTP 403 on mismatch) is NOT implemented in this PR by design; the trust boundary on Integrations Engine + DRF `HasProjectPermission` + `IntegrationsService.get_channel_app(...)` fail-closed `None` is the v1 enforcement gate, with the explicit cross-validation deferred to a separate `feat/tenant-isolation-cross-validation` PR. Each line above MUST cite the file diff that demonstrates compliance (e.g. "`retail/settings.py` diff is empty for new keys", "`retail/celery.py` diff is empty", "`retail/broadcasts/consumers/` diff is empty for tenant-resolution logic") so reviewers can verify in one read.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **BLOCKS** all user stories.
- **US1 (Phase 3)**: Depends only on Foundational. Sequential entry point for the rest of the work.
- **Spec correction (Phase 3.5)**: Depends on US1 (Phase 3) being complete (Phase 3.5 retroactively corrects the `direct_send` storage scheme introduced by US1's T002). **MUST run BEFORE Phase 4 (US2)** so US2 fixtures and implementation are authored against the canonical `IntegratedAgent.config["direct_send"]` JSON-key form from the start, AND **MUST run BEFORE Phase 7 (T036–T039)** so the polish/coverage/PR phase runs against the canonical shape from `data-model.md §1`, not the superseded column form. Strictly speaking the phase touches only the agents-side storage (US2/US3/US4 are independent of it for code correctness because their tasks already specify the JSON-key form per T104's "task description sweep"), but running it BEFORE US2 caps the surface T104 has to migrate at the existing US1 fixture set rather than letting US2/US3/US4 fixtures grow it.
- **User Stories (Phases 4–6)**: All depend on Foundational AND on Phase 3.5 being complete. After Phase 3.5, US2/US3/US4 run independently — sequentially (P2 → P3 → P4) for a single implementer or in parallel for a multi-developer team.
- **Polish (Phase 7)**: Depends on every desired user story being complete (Phases 3, 4, 5, 6) AND on Phase 3.5 being complete. Running T037 (coverage parity) or T039 (open PR) before Phase 3.5 would ship the wrong storage scheme.

### User Story Dependencies

- **US1 (P1)**: Depends only on Foundational (T002, T004, T007). Tested via fixtures; does not need US2's assignment flow. T014a (dedup regression), T014b (FR-031 official-agent precedence regression), and T014c (FR-030 different-`current_state` regression) additionally depend on T014 — the dispatch branching done by T014 is what allows the dedup and resolution mechanisms to admit a Direct Send-enabled IntegratedAgent end-to-end.
- **US2 (P2)**: Depends only on Foundational. Independent of US1's payload builder.
- **US3 (P3)**: Depends only on Foundational (T004 — the new statuses). Independent of US1 and US2.
- **US4 (P4)**: Depends only on Foundational. The legacy-cohort default (`direct_send=False`) holds because `obj.config.get("direct_send", False)` collapses absence-of-key to `False` for every pre-existing IntegratedAgent — no schema change is required. Pure regression-guard surface; no implementation tasks.

### Within Each User Story

- Tests (TDD) are written FIRST and MUST FAIL before the matching implementation task is run (Constitution Principle III + project SKILL).
- Models / migrations (foundational only) before services / use cases.
- Service / use-case tests before service / use-case implementation.
- Story complete and validated before moving to the next priority (or ship the MVP after US1).

### Parallel Opportunities

- T006, T007 (foundational, different files) can run in parallel after T002–T005.
- All `[P]` tests within a single phase touch different files and run in parallel. **Exception**: the T011/T011a–T011d cluster shares `test_broadcast_direct_send.py` (T011e lives in the sibling `test_broadcast_direct_send_persistence.py` so the persistence-focused fixtures stay separated from the wire-shape fixtures), the T018/T018a–T018e cluster shares `test_assign_direct_send.py`, and the T014a/T014c cluster shares `test_order_status_dedup_direct_send.py`. The sub-tasks within each cluster are still independent test methods on disjoint scenarios (naming-rule vs. empty-body vs. happy-path; same-tuple-dedup vs. different-`current_state`-dispatch; new-assignment vs. re-assignment-after-`is_active=False`, etc.), so they can be authored in any order by separate developers and merged sequentially without conflict; the `[P]` tag denotes task-level parallelism for multi-developer assignment, not file-level isolation.
- Different user stories run in parallel after Foundational (multi-developer setting).

---

## Parallel Example: User Story 2

```bash
# Tests for User Story 2 — all in different files, can run in parallel:
Task: "Tests for MetaClient.fetch_library_template_by_name_and_language in retail/clients/meta/tests/test_meta_client.py"
Task: "Tests for MetaService.fetch_library_template_by_name_and_language in retail/services/meta/tests/test_meta_service.py"
Task: "Tests for adapt_meta_library_template_response (pure adapter) and fetch_meta_library_template_metadata (Direct-Send wrapper) helpers in retail/templates/tests/usecases/test_meta_library_template_fetch.py"
Task: "Tests for AssignAgentUseCase Direct Send branch in retail/agents/tests/usecases/test_assign_direct_send.py (T018 / T018a–T018e — _resolve_direct_send_flag paths, happy path, pt_BR fallback, atomic rollback on both-languages-fail, atomic rollback on unsupported component, re-assignment after is_active=False)"
Task: "Tests for ReadIntegratedAgentSerializer exposing direct_send"

# Once tests are red, implementation tasks T020–T028 follow the call-graph order:
# T020 (Protocols) → T021 (Client) → T022 (Service) → T023 (Helper) → T024 (Refactor) → T025 (_resolve_direct_send_flag) → T026 (plumb flag) → T027 (Direct Send branch) → T028 (Serializer)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (US1) — the dispatch path.
3. **STOP and VALIDATE**: dispatch a Direct Send broadcast against a hand-crafted DB fixture (no assignment-flow changes yet). Verify the Flows payload matches `contracts/messaging-gateway-payload.md` §3.
4. Demo to stakeholders.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → MVP (Direct Send dispatch with hand-crafted fixtures).
3. Phase 3.5 → relocate `direct_send` to the canonical `IntegratedAgent.config` JSON-key form before any new fixtures are authored.
4. US2 → assignment flow auto-provisions templates locally.
5. US3 → broadcasts blocked on PAUSED/FLAGGED.
6. US4 → legacy regression guard pinned.
7. Polish → coverage parity, pre-commit, PR.

### Parallel Team Strategy

Phases 1, 2, 3, 3.5 run sequentially because Phase 3.5's storage relocation (T100–T106) gates US2/US3/US4 fixtures on the canonical `IntegratedAgent.config["direct_send"]` JSON-key form. Once Phase 3.5 is complete, with three developers:

- Developer A picks US2 (assignment flow).
- Developer B picks US3 (status block).
- Developer C picks US4 (legacy regression guard).

US4's regression tests intentionally have no implementation tasks; they pin the legacy shape that US1 / US2 must NOT alter. Surfaced regressions in any developer's branch are caught by US4's snapshot test.

---

## Notes

- `[P]` marks tasks that touch different files and have no incomplete-task dependencies.
- `[Story]` labels every user-story-phase task for traceability against `spec.md`.
- Each user story is independently completable and testable.
- Tests MUST be observed to FAIL before the matching implementation task runs (TDD discipline; Constitution Principle III).
- Commit after each task or logical group following Conventional Commits (`feat:`, `test:`, `refactor:`, `chore:`).
- Stop at any checkpoint to validate the story independently — the MVP exit point is the end of Phase 3.
- Any deviation from the constitution (Principles I–V) MUST be added to `Complexity Tracking` in `plan.md`. None is required by this task list.
