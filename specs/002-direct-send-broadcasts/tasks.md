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
- `[~]` — **Superseded**: the work was performed during an earlier phase but the canonical merge shape was relocated by a later phase. Used today by (a) Phase 3.5's relocation of `direct_send` from a model column to `IntegratedAgent.config` JSON, and (b) Phase 8's relocation of the Direct Send button wire shape from `msg.buttons[*].sub_type={"cta_url","reply"}` to the FR-014a / FR-014b top-level siblings on `msg` (`msg.interaction_type`, `msg.cta_message`, `msg.quick_replies`). A `[~]` task MUST NOT be re-executed on a fresh checkout; follow the explicit `SUPERSEDED by T...` cross-reference instead.

> ## ✅ OUTSTANDING WORK CLOSED (Phase 8 second extension — resolved 2026-05-22 by `/speckit-implement`)
>
> All Phase 8 **second** extension tasks (T116 / T117 / T118) have
> landed; the Phase 7 re-run gate completed clean for the
> second-extension scope:
>
> - **T116** (FR-014c) — `Broadcast.build_direct_send_message` now
>   drops `msg.template` from the Direct Send payload, emits the
>   local template name on the top-level sibling key
>   `msg.direct_send_template_name`, and omits locale from the wire
>   (no `msg.locale` / `msg.language`). The `send_message` logging
>   accessor and `_register_broadcast_event` were updated to be
>   path-aware so the Direct Send dispatch log line and the
>   downstream `BroadcastMessage` audit event continue to carry the
>   template name. Live code is at
>   `retail/agents/domains/agent_webhook/services/broadcast.py:804-820`.
> - **T117** (FR-014d) — the Direct Send wire body key was renamed
>   from `msg.body` to `msg.text`. The internal storage key
>   `Template.metadata["body"]`, the constant `MAX_BODY_LENGTH`, the
>   FR-039 audit-log discriminator `reason=empty_body`, and the
>   local variable `substituted_body` are preserved unchanged
>   (FR-014d(c) — wire-only rename).
> - **T118** (contract correction) — `contracts/messaging-gateway-payload.md`
>   §3.1 / §3.3 / §3.4 / §3.5 / §4 / §5.1 / §5.1b / §5.1c / §5.2 are
>   on disk in the canonical FR-014c / FR-014d shape. The T118
>   verification grep gate (`rg -n '"template":\s*\{|"body":\s*"|msg\.template|msg\.body|"locale":\s*"' contracts/messaging-gateway-payload.md`) returns
>   only matches inside §2.x (legacy path, allowed) or inside
>   explicit `**⚠️**` callout blocks. The T106 verification recipe
>   extension across `quickstart.md` / `research.md` / `data-model.md`
>   also returns only matches inside SUPERSEDED / Historical note /
>   `**⚠️**` blocks.
>
> Phase 7 re-run gate status (T036 / T037 / T038 / T039):
>
> - **T036** — quickstart validation: covered by the updated
>   persistence test
>   `test_full_template_with_header_footer_buttons_persists_and_dispatches`
>   (`retail/agents/tests/services/test_broadcast_direct_send_persistence.py`)
>   which exercises a full Direct Send dispatch and asserts (a) NO
>   `msg.template` key, (b) `msg.direct_send_template_name` carries
>   the local template name, (c) NO `msg.body` key, (d) `msg.text`
>   carries the substituted body, (e) NO `msg.locale` / `msg.language`
>   keys. The combined-case CTA URL + image header coverage from the
>   first extension is retained.
> - **T037** — `poetry run python contrib/compare_coverage.py`
>   reported `Number of test lines increased by 10` after the
>   second-extension landed (the new `BuildDirectSendMessageTemplateNameWireShapeTest`
>   and `BuildDirectSendMessageBodyTextRenameWireShapeTest` classes
>   plus the persistence-side `test_template_metadata_body_storage_key_is_preserved`
>   and `test_send_message_log_line_carries_direct_send_template_name`
>   methods are net-new with no `[~] SUPERSEDED` offset).
> - **T038** — pre-commit clean (Black + flake8) on
>   `broadcast.py`, `test_broadcast_direct_send.py`,
>   `test_broadcast_direct_send_persistence.py`,
>   `test_broadcast_legacy_payload.py`, and
>   `test_assign_direct_send.py`.
> - **T039** — PR body update tracked separately when the PR is
>   opened.
>
> ## ✅ PRIOR OUTSTANDING WORK CLOSED (Phase 8 first extension — resolved 2026-05-22 by `/speckit-implement`)
>
> All Phase 8 **first** extension tasks (T112, T113, T114) and the
> T014d unpause-race coverage have landed. The Phase 7 re-run gate
> completed clean for the first-extension scope only:
>
> - **T036** — quickstart validation (first-extension scope only):
>   covered by the new combined-case regression test
>   `test_combined_url_and_quick_replies_emit_parallel_siblings`
>   (T114(f)) which exercises a CTA URL + QUICK_REPLY template
>   end-to-end through `Broadcast.build_direct_send_message` and
>   confirms the captured payload carries `msg.interaction_type` +
>   `msg.cta_message` + `msg.quick_replies` as parallel siblings
>   with NO `msg.buttons` key. **⚠️ Second-extension scope (T116 /
>   T117) is not yet covered** — see the OUTSTANDING WORK BEFORE
>   MERGE block above.
> - **T037** — `poetry run python contrib/compare_coverage.py`
>   reported "Number of test lines increased by 10" (the T011a
>   `[~] SUPERSEDED` removal of the old QUICK_REPLY assertions was
>   offset by the new `BuildDirectSendMessageQuickReplyWireShapeTest`
>   class plus T112's override-map branches and T113's CTA URL
>   branches). Must re-run after T116 / T117 land.
> - **T038** — pre-commit clean on every changed file (Black +
>   flake8) for the first-extension scope.
> - **T039** — PR body update tracked separately when the PR is
>   opened.
> - **T115** — contract artifact (`messaging-gateway-payload.md`)
>   canonical for the first-extension scope only; the verification
>   grep `rg -n 'sub_type":\s*"cta_url"|sub_type":\s*"reply"'
>   contracts/messaging-gateway-payload.md` returns zero matches.
>   The second-extension grep gate (`"template":\s*\{` and
>   `"body":\s*"` inside Direct Send §3.x / §5.x) is delivered by
>   T118 and remains outstanding.

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

**Independent Test**: With a fixture `IntegratedAgent` whose `config.get("direct_send", False) is True` (per Phase 3.5's canonical JSON-key storage — `data-model.md §1`) and a `Template` whose `current_version.status="APPROVED"` and metadata carries body / header / footer / buttons, fire `Broadcast.build_message(integrated_agent, lambda_data)` and assert the returned dict matches the canonical Direct Send wire shape (post-Phase 8 first + second extensions): (a) `msg["direct_send"] is True` and `msg["category"] == "utility"`; (b) the substituted body content is carried under `msg["text"]` with all `{{N}}` placeholders replaced by the values from `lambda_data["template_variables"]` AND `"body" not in msg` (FR-014d); (c) the local template name is carried under `msg["direct_send_template_name"] == template.current_version.template_name` AND `"template" not in msg` (FR-014c / FR-014c(g)); (d) NO `msg["locale"]` and NO `msg["language"]` on the wire (FR-014c(f)); (e) CTA URL buttons (when present) are emitted as `msg["interaction_type"] == "cta_url"` + `msg["cta_message"] == {display_text, url}` siblings (FR-014a) and QUICK_REPLY buttons (when present) are emitted as `msg["quick_replies"] == ["title 1", ...]` (FR-014b); (f) `msg["buttons"]` is ABSENT from the Direct Send payload (combined FR-014a / FR-014b LEGACY-ONLY rule).

### Tests for User Story 1 (TDD — write FIRST, ensure FAIL before implementation)

- [X] T010 [P] [US1] Tests for `direct_send_payload_builder` in `retail/agents/tests/services/test_direct_send_payload_builder.py` covering: variable substitution with `{{1}}`/`{{2}}` replaced from a positional dict (regex `\{\{\s*(\d+)\s*\}\}`, whitespace-tolerant), missing-index logs WARNING and substitutes empty string, extra-index silently ignored (spec edge cases); `is_valid_direct_send_template_name` returns True for snake_case names ≤512 chars and False for names with hyphens/uppercase/length>512 (research Decision 7).
- [X] T011 [P] [US1] **Happy-path wire shape** — Tests for `Broadcast.build_direct_send_message` in `retail/agents/tests/services/test_broadcast_direct_send.py` covering Story 1 AS1, AS2, AS3. **AS1**: body with `{{1}}`/`{{2}}` substituted, `template.locale` from template metadata, `template.name` equals `Version.template_name`, `msg["direct_send"] is True`, `msg["category"] == "utility"` — Python dict notation; the wire JSON renders these as `"direct_send": true` and `"category": "utility"` per `contracts/messaging-gateway-payload.md` §3.1. **AS2**: image header + CTA URL button, URL with `{{1}}` substituted, `msg.header.image_url` AND `msg.attachments[0]` both set to the same value per contract §3.1 / §3.2. **AS3**: body-only template, no buttons / header / footer / variables.

  **⚠️ Wire-shape overlay — Phase 8 second extension / T116 / T117 (FR-014c / FR-014d)**: AS1's "`template.locale` from template metadata, `template.name` equals `Version.template_name`" assertion AND the implicit `msg["body"] == substituted_body` happy-path assertion describe the **pre-FR-014c / pre-FR-014d wire shape**. On a fresh checkout the canonical Direct Send wire shape is now: NO `msg.template` key (FR-014c(a)); `msg.direct_send_template_name == "<Version.template_name>"` as a top-level sibling on `msg` (FR-014c(g)); NO `msg.locale` / `msg.language` (FR-014c(f)); NO `msg.body` key (FR-014d(a)); `msg.text == "<substituted body>"` as a top-level sibling on `msg` (FR-014d(a)+(b)). T011's `[X]` marker reflects the original (pre-FR-014c / pre-FR-014d) implementation only — the live code at `broadcast.py:807, 808, 811` still emits the deprecated shape that the spec explicitly flags as an error. The canonical merge shape is delivered by T116 (drop `msg.template` + add `msg.direct_send_template_name` + drop wire locale) and T117 (rename `msg.body` → `msg.text`). The body / header.image_url / attachments substitution clauses, the `msg.direct_send=true` / `msg.category="utility"` clauses, and AS2's image-header + CTA URL combined-case shape remain authoritative as written (AS2's CTA URL was relocated by T113 to `msg.interaction_type` + `msg.cta_message` per the FR-014a overlay that the T013 / T113 cluster already pins).

  **⚠️ Coverage-state callout (pinned 2026-05-22 by `/speckit-analyze`)**: until T116 + T117 land, the canonical-shape happy-path assertions (`"template" not in msg`, presence of `msg.direct_send_template_name`, `"body" not in msg`, presence of `msg.text`) have **zero test coverage in the repository** — T011's `[X]` assertions exercise only the pre-FR-014c / pre-FR-014d wire shape, which is itself SUPERSEDED. The body-substitution / image-header / attachments / category clauses are unaffected and remain canonically covered by T011. See the OUTSTANDING WORK BEFORE MERGE banner at the top of this file.
- [~] T011a [P] [US1] **⚠️ SUPERSEDED by T114 (Phase 8)** — Original task body: **Quick-reply buttons** — Tests in the same file (`test_broadcast_direct_send.py`) covering quick-reply button rendering: up to 3 `QUICK_REPLY` buttons rendered with `sub_type="reply"`, `id`, `title` per contract §3.3; at least one title contains `{{1}}` and is substituted via the helper (Decision 6). Assert the resulting button list preserves order and that titles ≤ 20 chars survive the post-substitution length gate from T013. **The `[~]` marker means "the original asserted shape is no longer canonical"**: spec FR-014b (Session 2026-05-22 Q10) relocates QUICK_REPLY emission from objects inside `msg.buttons` to a flat `msg.quick_replies = ["title 1", ...]` array on `msg`, drops the `id` field on the wire entirely, and forbids the Direct Send path from emitting any `msg.buttons` key at all (combined with FR-014a). The canonical merge shape is delivered by T114 (Phase 8); do not re-author the original `sub_type="reply"` assertions on a fresh checkout. The references "(Decision 6)" and "per contract §3.3" inside this body are pre-FR-014b and remain only for git-history readability — `contracts/messaging-gateway-payload.md` §3.3 is itself corrected by T115 against the new shape.

  **⚠️ Coverage-state callout (pinned 2026-05-22 by `/speckit-analyze`)**: until T114 lands, the `[~]` supersession is structurally incomplete — the original assertions have been retired from the coverage floor but the replacements do not yet exist. **QUICK_REPLY canonical-shape coverage is currently NIL in the repository.** A reviewer scanning the `[~]` marker for completion status MUST read this callout AND confirm T114 has been executed before merge. See the OUTSTANDING WORK BEFORE MERGE banner at the top of this file.
- [X] T011b [P] [US1] **Refusal — naming-rule violation** — Tests in the same file covering the FR-017 skip path: a template whose `Version.template_name` contains uppercase / hyphens / non-ASCII characters or exceeds 512 chars MUST cause `build_direct_send_message` to return `None` AND emit the audit log line `[BroadcastDispatch] skipped_due_to_direct_send_validation: project_uuid={integrated_agent.project.uuid} agent={...} template={...} reason=naming_rule event={data}` (FR-039 mandates `project_uuid` as a top-level key; Decision 7). Capture with `assertLogs` at WARNING level and assert the literal `reason=naming_rule` substring is present.

  **⚠️ FR-014c(d) audit-not-affected note (pinned 2026-05-22 by `/speckit-analyze`)**: the audit-log `template={template_name}` field above is **INTERNAL observability**, NOT the wire. The FR-014c relocation (drop `msg.template`, add `msg.direct_send_template_name`) applies EXCLUSIVELY to the outbound `msg.*` payload sent to Flows; it does NOT rename the audit-log discriminator. A future T116 / T117 implementer MUST NOT cargo-cult the FR-014c rename into `[BroadcastDispatch] skipped_due_to_direct_send_validation: ... direct_send_template_name=...` — the audit log keeps its existing `template={template_name}` field for log-consumer stability per FR-027. T011b's `[X]` assertions remain canonical and authoritative; the FR-014c second-extension fold-in does NOT supersede them.
- [X] T011c [P] [US1] **Refusal — empty body / length limits** — Tests in the same file covering the contract §4 rule-2 and rule-3 refusal paths: (i) `template.metadata.body` missing or empty → `None` + audit log with `reason=empty_body` (`contracts/messaging-gateway-payload.md` §4 rule 2); (ii) post-substitution component length-limit overflow → `None` + audit log with `reason=component_length_limit` when the substituted body > 1024, header.text > 60, footer > 60, button `display_text` (cta_url) > 20, or button `title` (reply) > 20 (constants from `direct_send_constants.py`); (iii) button `url` is NOT length-checked at this gate — a substituted URL > 20 chars MUST dispatch normally (URLs can be up to 2000 chars per `contracts/messaging-gateway-payload.md` §3.3). All log lines carry `project_uuid` as a top-level key per FR-039.

  **⚠️ Refusal-location overlay — Phase 8 / T113 / T114 (FR-014a / FR-014b)**: clauses (ii) and (iii) above describe the pre-FR-014a/FR-014b wire shape (the length checks ran against `msg.buttons[*].display_text` and `msg.buttons[*].title`). On a fresh checkout the canonical refusal LOCATIONS are: `cta_message.display_text` ≤ `MAX_BUTTON_LABEL_LENGTH` (T113(d)) and `quick_replies[*]` ≤ `MAX_BUTTON_LABEL_LENGTH` post-substitution (T114(e)). The `reason=component_length_limit` discriminator and the audit-log shape are unchanged; only the LOCATION the limit is read from is relocated. T011c's existing `[X]` tests remain authoritative for body / header.text / footer / `url` (clauses i / ii body+header+footer / iii); the button-side clause (ii — `display_text` / `title`) is overlaid by T113(d) and T114(e) on the new wire-shape locations.

  **⚠️ Coverage-state callout (pinned 2026-05-22 by `/speckit-analyze`)**: until T113 + T114 land, the canonical-shape length-limit refusals (`cta_message.display_text` and `quick_replies[*]`) have **zero test coverage in the repository** — T011c's `[X]` button-side assertions exercise only the pre-FR-014a/FR-014b `msg.buttons[*]` locations, which are themselves SUPERSEDED. The non-button-side clauses (body / header.text / footer / `url`) remain canonically covered by T011c and are unaffected. See the OUTSTANDING WORK BEFORE MERGE banner at the top of this file.
- [X] T011d [P] [US1] **No-local-template edge case** — Test in the same file covering the spec edge case "Direct Send-enabled agent with no local template for the rule": given a Direct Send-enabled `IntegratedAgent` and a `data["template"]` that does NOT exist in `integrated_agent.templates`, `Broadcast.build_message` returns `None`, `build_direct_send_message` is never invoked, no payload is built, no `BroadcastMessage` row is persisted, and a `WARNING` line matching the substring `"not found"` is emitted by the dispatch flow (FR-027 — after US3's T031 consolidation, this assertion is satisfied by `Broadcast.build_message`'s downstream "Template not found or has no approved current version" line, which remains the legacy shape; the upstream `Broadcast.get_current_template` per-name miss now emits the unified `[BroadcastDispatch] skipped_due_to_status: ... version_status=NOT_FOUND ...` audit shape per FR-039's "Dispatch-gate skip (unified shape)" entry).
- [X] T011e [P] [US1] **BroadcastMessage persistence parity** — End-to-end test in `retail/agents/tests/services/test_broadcast_direct_send_persistence.py` (sibling to `test_broadcast_direct_send.py` so the persistence-focused fixtures stay separated from the wire-shape fixtures and the file does not grow past comfortable review size) that drives `Broadcast.build_message` → existing dispatch wiring against a Direct Send-enabled fixture and asserts (a) a `BroadcastMessage` row is persisted with the expected `status`, `template_name`, `contact_urn`, and `integrated_agent` on the happy path (FR-016, SC-005); (b) NO `BroadcastMessage` row is persisted on EACH refusal class exercised by T011b–T011c (naming-rule, empty body, length limit — contract §4). Use a mocked `flows_service.send_whatsapp_broadcast` to capture (a)'s outbound call without hitting Flows.

### Implementation for User Story 1

- [X] T012 [US1] Create `retail/agents/domains/agent_webhook/services/direct_send_payload_builder.py` with: `substitute_template_variables(text: str, variables: Dict[str, Any], *, template_name: str) -> str` (regex `\{\{\s*(\d+)\s*\}\}` — whitespace-tolerant; missing index→`""` + WARNING log, extra index→ignored); `is_valid_direct_send_template_name(name: str) -> bool` (regex `^[a-z0-9_]+$`, length ≤ 512); helper builders for header / footer / buttons that consume the `Template.metadata` shape produced by `_get_template_info`. Import the Direct Send length-limit constants (`MAX_BODY_LENGTH`, `MAX_HEADER_TEXT_LENGTH`, `MAX_FOOTER_LENGTH`, `MAX_BUTTON_LABEL_LENGTH`) from `retail/agents/domains/agent_webhook/services/direct_send_constants.py` (created in T007a) so T013 (post-substitution dispatch-time check) and T023 (pre-substitution assignment-time check) share the same source of truth (research Decision 6 / Decision 8; contracts/meta-library-catalog.md §5).
- [X] T013 [US1] Implement `Broadcast.build_direct_send_message` in `retail/agents/domains/agent_webhook/services/broadcast.py` matching the shape in `contracts/messaging-gateway-payload.md` §3: substitute body / header.text / footer / buttons[*].url / buttons[*].title via the helper; when `template.metadata["header"]["type"] == "IMAGE"`, set `msg.header = {"type": "image", "image_url": data["template_variables"]["image_url"]}` AND append `f"image/jpeg:{image_url}"` (mirroring the s3-keyed shape produced by `build_broadcast_template_message`) to `msg.attachments` for downstream parity — both representations are required by contracts/messaging-gateway-payload.md §3.1 ("`attachments`: conditional — required when `header.type == "image"`") and §3.2 ("Same value MUST also appear in `msg.attachments[0]`"); emit `msg.direct_send=true`, `msg.category="utility"`; refuse to emit (return `None` + audit-log entry with format `[BroadcastDispatch] skipped_due_to_direct_send_validation: project_uuid={integrated_agent.project.uuid} agent={...} template={...} reason={naming_rule|empty_body|component_length_limit} event={data}` — FR-039 mandates `project_uuid` as a top-level key) when (a) the template name fails `is_valid_direct_send_template_name`, (b) `template.metadata.body` is missing/empty, or (c) any post-substitution component exceeds Meta's documented length limits — body ≤ `MAX_BODY_LENGTH` (1024), header.text ≤ `MAX_HEADER_TEXT_LENGTH` (60), footer ≤ `MAX_FOOTER_LENGTH` (60), button `display_text` (cta_url) and button `title` (reply) ≤ `MAX_BUTTON_LABEL_LENGTH` (20). Note: button `url` is NOT subject to the 20-char limit per `contracts/messaging-gateway-payload.md` §3.3 — `display_text` is the only `cta_url` field with a 20-char ceiling, and the URL itself can be much longer (Meta allows up to 2000 chars). Reuse the length constants from `direct_send_constants.py` (T007a) so the dispatch-time limits and the assignment-time validation (T023) share a single source of truth.

  **⚠️ Button-emission overlay — Phase 8 / T113 / T114 (FR-014a / FR-014b)**: the button-substitution clauses above ("substitute … buttons[*].url / buttons[*].title", "button `display_text` (cta_url) and button `title` (reply) ≤ `MAX_BUTTON_LABEL_LENGTH`") describe the pre-FR-014a/FR-014b wire shape (objects inside `msg.buttons`). On a fresh checkout the canonical Direct Send wire shape is now: CTA URL → `msg.interaction_type="cta_url"` + `msg.cta_message={display_text, url}` (FR-014a); QUICK_REPLY → flat `msg.quick_replies=["title 1", ...]` array (FR-014b); `msg.buttons` is LEGACY-ONLY and the Direct Send path NEVER emits it. T013 is preserved verbatim for git-history continuity, but its button-emission and length-check clauses are SUPERSEDED by T113 (CTA URL relocation + `_exceeds_direct_send_length_limits` reads from `msg.cta_message.display_text`) and T114 (QUICK_REPLY relocation + `_exceeds_direct_send_length_limits` iterates `msg.quick_replies`). The body / header.text / footer / image-header substitution clauses, the `msg.direct_send=true` / `msg.category="utility"` / `msg.attachments` clauses, the audit-log refusal shape, and the `MAX_BODY_LENGTH` / `MAX_HEADER_TEXT_LENGTH` / `MAX_FOOTER_LENGTH` / `MAX_BUTTON_LABEL_LENGTH` length-constant reuse remain authoritative as written.

  **⚠️ Body / template-name wire-shape overlay — Phase 8 second extension / T116 / T117 (FR-014c / FR-014d)**: the "emit `msg.direct_send=true`, `msg.category="utility"`" clauses above are unaffected by the second extension and remain authoritative — but the implicit "`msg["template"] = {"name": template_name}`" + "`msg["body"] = substituted_body`" emissions that T013 ships today (live at `broadcast.py:807-808`) describe the pre-FR-014c / pre-FR-014d wire shape. On a fresh checkout the canonical Direct Send wire shape is now: NO `msg.template` key (FR-014c(a)); `msg.direct_send_template_name = "<template_name>"` as a top-level sibling on `msg` (FR-014c(g)); NO `msg.locale` / `msg.language` on the wire (FR-014c(f)); NO `msg.body` key (FR-014d(a)); `msg.text = "<substituted body>"` as a top-level sibling on `msg` (FR-014d(a)+(b)). T013's template-name and body emissions are SUPERSEDED by T116 (drop `msg.template`, add `msg.direct_send_template_name`, drop wire locale) and T117 (rename wire key `msg.body` → `msg.text`).

  **⚠️ FR-014c(d) / FR-014d(c) audit-not-affected note (pinned 2026-05-22 by `/speckit-analyze`)**: the `[BroadcastDispatch] skipped_due_to_direct_send_validation: ... template={...} ... reason={naming_rule|empty_body|component_length_limit} ...` audit-log shape above is **INTERNAL observability**, NOT the wire. The FR-014c relocation does NOT rename the audit-log `template={...}` field (FR-014c(d) — wire-only rename); the FR-014d rename does NOT change the audit-log refusal-reason discriminator `reason=empty_body` (FR-014d(c) — wire-only rename, the discriminator stays as `empty_body` even though the wire key is now `text`). The internal length constants `MAX_BODY_LENGTH` / `MAX_HEADER_TEXT_LENGTH` / `MAX_FOOTER_LENGTH` / `MAX_BUTTON_LABEL_LENGTH` MUST remain unchanged in `direct_send_constants.py` (FR-014d(c) preserves `MAX_BODY_LENGTH` by name and value). T013's audit-log clauses and length-constant clauses remain canonical and authoritative; T116 / T117 do NOT supersede them.

  **⚠️ Implementation-state callout (pinned 2026-05-22 by `/speckit-analyze`)**: T013's `[X]` marker reflects the original (pre-FR-014a / pre-FR-014b / pre-FR-014c / pre-FR-014d) implementation only. Inspection of `retail/agents/domains/agent_webhook/services/broadcast.py:796-818` confirms the live code still writes `msg["buttons"] = buttons` and `_exceeds_direct_send_length_limits` (lines 820-850) still iterates `msg.buttons[*]` (T013 → T113 / T114 violations); the same line range also still writes `msg["template"] = {"name": template_name}` + `msg["template"]["locale"] = language` + `msg["body"] = substituted_body` (T013 → T116 / T117 violations). **Every Direct Send dispatch emitted today violates FR-014a, FR-014b, FR-014c, AND FR-014d on the wire.** The canonical shape is delivered by T113 + T114 (first extension) and T116 + T117 (second extension); until ALL FOUR tasks land, the `[X]` marker on T013 covers only the audit-log refusal shape and the length-constant clauses listed above. See the OUTSTANDING WORK BEFORE MERGE banner at the top of this file.
- [X] T014 [US1] Branch `Broadcast.build_message` in `retail/agents/domains/agent_webhook/services/broadcast.py` so that when `integrated_agent.direct_send` is `True` it calls `build_direct_send_message`; otherwise it keeps calling the existing `build_broadcast_template_message` unchanged (research Decision 11). No changes are required to `Broadcast.send_message` (`retail/agents/domains/agent_webhook/services/broadcast.py:391`) — it consumes the result of `build_message` only via `message.get("msg", {}).get("template", {}).get("name", ...)` for logging, then forwards the entire `message` dict to `flows_service.send_whatsapp_broadcast(message)`. The Direct Send payload preserves both `msg.template` and `msg.template.name` (per `contracts/messaging-gateway-payload.md` §3.1), so `send_message` is generic over the new dict shape and the `BroadcastMessage` persistence path (`_register_broadcast_event` + `_record_broadcast_message`) works unchanged. T011e's "end-to-end build_message → existing dispatch wiring" assertion is satisfied without modifying `send_message`.

  **⚠️ `send_message` logging-line overlay — Phase 8 second extension / T116 (FR-014c)**: the claim above that "the Direct Send payload preserves both `msg.template` and `msg.template.name`" is **the pre-FR-014c statement** and is canonically SUPERSEDED. After T116 lands, the Direct Send payload MUST NOT carry `msg.template` at all (FR-014c(a)); the local template name moves to the top-level sibling key `msg.direct_send_template_name` (FR-014c(g)). The current `send_message` logging accessor `message.get("msg", {}).get("template", {}).get("name", ...)` will resolve to the fallback on the Direct Send path after T116, which means the dispatch log line emits an empty template name for every Direct Send broadcast unless updated. T116's implementation contract therefore extends T014's "no changes to `send_message`" stance — `send_message` MUST be updated to a path-aware accessor (recommended form: `template_name = message.get("msg", {}).get("direct_send_template_name") or message.get("msg", {}).get("template", {}).get("name", "")`) so the Direct Send path logs via `msg.direct_send_template_name` and the legacy path continues to log via `msg.template.name` byte-identically per FR-027. The `BroadcastMessage` persistence path (`_register_broadcast_event` + `_record_broadcast_message`) does NOT read `msg.template.name`; it reads the template name from a sibling argument, so persistence semantics are unaffected by T116 / T117. T011e's end-to-end assertion still passes after T116 / T117 land (with the path-aware accessor in place); T116(h) pins the path-aware-accessor behaviour with explicit `assertLogs` coverage for both cohorts.
- [X] T014a [P] [US1] Add a regression test for FR-028 duplicate-trigger suppression on the Direct Send path in `retail/agents/tests/usecases/test_order_status_dedup_direct_send.py`. With a Direct Send-enabled `IntegratedAgent` fixture and `@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "test-direct-send-dedup"}})` (Constitution Principle III), invoke `AgentOrderStatusUpdateUsecase.execute(...)` twice in a row with the SAME canonical idempotency tuple `(Project, IntegratedAgent.uuid, OrderStatusDTO.orderId, OrderStatusDTO.currentState)` (the `Project` component is identified by its FK integer or UUID per FR-028's serialization rule). Assert: (a) exactly one outbound `flows_service.send_whatsapp_broadcast` call is made (mocked with `MagicMock(spec=...)`); (b) exactly one `BroadcastMessage` row is persisted; (c) the second invocation emits the INFO log shape `[ORDER_STATUS] duplicate_skipped: vtex_account={...} agent_uuid={...} current_state={...} order_id={...}` (captured with `assertLogs` at INFO level — FR-039 dedup-skip shape); (d) **dedup cache key shape (FR-029 normative components)** — wrap `django.core.cache.cache.add` with `unittest.mock.patch("django.core.cache.cache.add", wraps=cache.add)` (or capture via a `MagicMock(side_effect=cache.add)` on the import alias used in `_is_duplicate_event`), invoke `execute` once more with a fresh tuple, and assert the captured positional `cache_key` argument matches the regex `^order_status_event:[^:]+:[0-9a-f-]{36}:[^:]+:[^:]+$` AND that splitting on `:` yields exactly five segments — the literal prefix plus the four normative components `(project, integrated_agent.uuid, order_id, current_state)`. The second segment intentionally uses `[^:]+` (rather than `\d+`) so the test passes whether the implementation serializes `project` as the FK integer (`project_id`) or as the UUID — both are spec-compliant per FR-028's serialization rule. This pins FR-028 + FR-029 + FR-030 + FR-039's dedup-skip shape for the Direct Send cohort. Without (d), a future refactor that scopes the dedup key by `direct_send` (or drops `current_state`, or adds a fifth component, or removes one of the four) would silently invalidate the spec's "components are normative" claim and would not be caught by any other test. **Legacy-cohort coverage** (FR-028 last sentence — "applies identically to the Direct Send path and the legacy path"): the legacy cohort is already covered by the pre-feature dedup tests in `retail/agents/tests/usecases/test_order_status_update.py` (`test_execute_skips_duplicate_event_within_window` and the `test_*_cache_key_*` group at lines 297–396, which exercise `mock_cache.add` with the same `(project_id, integrated_agent.uuid, order_id, current_state)` shape). T014a explicitly does NOT replace those tests — it is the Direct Send-specific regression guard that runs alongside them; both cohorts together pin FR-028 across the path-selection branch added by T014.
- [X] T014b [P] [US1] Add a regression test for FR-031 official-agent precedence on the Direct Send cohort in `retail/agents/tests/usecases/test_order_status_agent_resolution_direct_send.py`. With two `IntegratedAgent` fixtures BOTH on `direct_send=True` for the same `Project` — (i) one whose `agent.uuid == settings.ORDER_STATUS_AGENT_UUID` (the official OrderStatus agent), (ii) one whose `parent_agent_uuid` flags it as a custom OrderStatus agent — invoke the order-status webhook entry point with a payload that would match BOTH. Assert: (a) exactly one outbound `flows_service.send_whatsapp_broadcast` call is made (mocked); (b) exactly one `BroadcastMessage` row is persisted; (c) the persisted row's `integrated_agent` FK points at the OFFICIAL fixture (i), NEVER the custom fixture (ii); (d) the audit log contains `[ORDER_STATUS] agent_resolved: vtex_account={...} agent_uuid={official_uuid} source=official` and does NOT contain `source=parent_agent` for this event.

  **Pre-condition (verified at task authoring time)**: the production code at `retail/agents/domains/agent_webhook/usecases/order_status.py:105-109` and `:124-130` already emits the two `[ORDER_STATUS] agent_resolved: vtex_account={...} agent_uuid={...} source={official|parent_agent}` lines documented by FR-039. T014b is therefore a **pure regression pin**, not a code-change task — no production code edit is required for the test to pass on green main. If a future PR moves `_lookup_order_status_agent` and the log line drifts (rename, missing `source=` discriminator, swapped order), T014b will fail; the correct remediation is to **restore the log line shape in production code** (FR-039 makes the shape normative), not to relax the test. Implementers MUST NOT silence T014b by adding/removing fields on the assertion side.

  **Tenant-key note**: the `vtex_account={...}` (rather than `project_uuid={...}`) shape is intentional and spec-compliant per FR-039 (the agent-resolution admission shape is emitted at the entry point alongside the dedup shape, where the project has not yet been resolved) plus FR-044's legacy-preservation rule (existing `vtex_account`-keyed lines stay as-is; `project_uuid` MAY be added additively but is NOT required by this feature). A reviewer who flags the `vtex_account`-only key as a tenant-isolation regression should be referred to FR-044. This pins FR-031 specifically for the Direct Send cohort — without it, a future refactor that re-routed Direct Send-enabled agents through a separate resolution path (e.g. "Direct Send custom agents win") would silently break FR-031 and would not be caught by the existing legacy-cohort tests of `_lookup_order_status_agent`.
- [X] T014c [P] [US1] Add an FR-030 positive-path behavioral test in `retail/agents/tests/usecases/test_order_status_dedup_direct_send.py` (sibling test method on the file authored by T014a). With a Direct Send-enabled `IntegratedAgent` fixture and `@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "test-direct-send-fr030"}})` (Constitution Principle III), invoke `AgentOrderStatusUpdateUsecase.execute(...)` twice with the SAME `(project, integrated_agent.uuid, order_id)` triple but DIFFERENT `current_state` values (e.g. `invoiced` followed by `shipped`). Assert: (a) exactly TWO outbound `flows_service.send_whatsapp_broadcast` calls are made (mocked with `MagicMock(spec=...)`); (b) exactly TWO `BroadcastMessage` rows are persisted, each with the corresponding `current_state`; (c) the two dedup cache keys are DISTINCT — capture them via `unittest.mock.patch("django.core.cache.cache.add", wraps=cache.add)` and assert the two captured `cache_key` arguments are unequal AND that they share the first four `:`-separated segments (project, integrated_agent.uuid, order_id) but differ in the fifth (current_state). This pins FR-030 ("two events differing ONLY in `current_state` MUST both be dispatched as separate logical broadcasts") DIRECTLY for the Direct Send cohort. T014a covers the inverse case (same tuple → 1 dispatch via dedup); T014c covers the difference-in-`current_state` path. Without T014c, FR-030 is only structurally guaranteed by T014a's cache-key-shape assertion (the key includes `current_state` as a component) — which is sound but transitive; T014c makes the behavior assertable directly so a future refactor that collapses the dedup key by dropping `current_state` would fail the test instead of silently merging two distinct logical broadcasts into one.
- [X] T014d [P] [US1, US3] **Unpause-race coverage** (spec Edge Case "PAUSED → APPROVED transition lands DURING the dedup window of an in-flight broadcast for the same template" — pinned 2026-05-22 by `/speckit-analyze`) — Sibling test method on `retail/agents/tests/usecases/test_order_status_dedup_direct_send.py` (the file authored by T014a — adding a third method keeps the dedup-window-related fixtures co-located so the file stays the canonical home for FR-028 / FR-029 / FR-030 + unpause-race coverage). With a Direct Send-enabled `IntegratedAgent` fixture, a `Template` whose `current_version.status` starts at `PAUSED`, and `@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "test-direct-send-unpause-race"}})` (Constitution Principle III), invoke `AgentOrderStatusUpdateUsecase.execute(...)` ONCE with the canonical idempotency tuple — assert (a) the dispatch is skipped via the FR-039 unified `[BroadcastDispatch] skipped_due_to_status: ... version_status=PAUSED ...` audit shape; (b) `flows_service.send_whatsapp_broadcast` is NOT called; (c) NO `BroadcastMessage` row is persisted; (d) the dedup cache key IS populated (the dedup gate accepted the event before the version-status read — see spec Edge Case last sentence). Then flip `version.status = "APPROVED"` and `save()` (simulating the unpause race) and invoke `execute(...)` AGAIN with the SAME `(project, integrated_agent.uuid, order_id, current_state)` tuple within the dedup window — assert (e) the second invocation observes the existing dedup cache key and skips with the FR-028 `[ORDER_STATUS] duplicate_skipped: ...` audit shape; (f) `flows_service.send_whatsapp_broadcast` is STILL not called; (g) NO `BroadcastMessage` row is persisted. This pins the spec's "an event that arrived during the dedup window of an earlier PAUSED-skip will NOT auto-replay; the next webhook is the trigger" guarantee against a future refactor that moved the version-status read BEFORE the dedup cache write (which would silently re-fire the dispatch on unpause). The cost is one extra test method; the regression surface is the spec edge case verbatim.

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

      **⚠️ Verification-recipe extension (Phase 8 — 2026-05-22)**:
      after the Phase 8 first extension lands (T112–T115), the
      verification recipe MUST also confirm the FR-014a / FR-014b /
      FR-003g fold-in did not leak the deprecated wire-shape into
      `quickstart.md` / `research.md` / `data-model.md`. Run:

      ```bash
      rg -n 'sub_type":\s*"cta_url"|sub_type":\s*"reply"|msg\.buttons\[\*\]\.(?:display_text|title)' \
        specs/002-direct-send-broadcasts/quickstart.md \
        specs/002-direct-send-broadcasts/research.md \
        specs/002-direct-send-broadcasts/data-model.md \
        specs/002-direct-send-broadcasts/contracts/
      ```

      All matches MUST land inside an explicit "SUPERSEDED" /
      "Historical note" / "**⚠️**" block OR inside §2 of
      `contracts/messaging-gateway-payload.md` (the legacy-path
      section is bit-for-bit preserved per FR-020 and intentionally
      retains the legacy `sub_type: "url"` / `sub_type: "payment_request"`
      shapes — those are NOT what this gate watches for; the gate
      watches for `cta_url` / `reply` on the Direct Send path
      specifically). Any survivor outside those exempted contexts
      is a documentation drift and a follow-up patch is required
      before merge. Cross-check the override map: run
      `rg -n 'DIRECT_SEND_BUTTON_LABEL_OVERRIDES|order_canceled_3.*pt_BR|order_canceled_3.*es' specs/002-direct-send-broadcasts/`
      and confirm each operator-facing artefact (`quickstart.md`,
      `research.md`, `data-model.md`) cites the map per FR-003g(g)
      (initial map content is normative and the map's contents are
      a spec-amendment surface).

      **⚠️ Verification-recipe second extension (Phase 8 second
      extension — pinned 2026-05-22 by `/speckit-analyze`)**: after
      the Phase 8 second extension lands (T116–T118), the
      verification recipe MUST also confirm the FR-014c / FR-014d
      fold-in did not leak the deprecated wire-shape into the
      operator-facing artefacts. Run:

      ```bash
      rg -n '"template":\s*\{|"body":\s*"|msg\.template\.(?:name|locale)|msg\.body|msg\.locale|msg\.language' \
        specs/002-direct-send-broadcasts/quickstart.md \
        specs/002-direct-send-broadcasts/research.md \
        specs/002-direct-send-broadcasts/data-model.md \
        specs/002-direct-send-broadcasts/contracts/
      ```

      All matches MUST land inside an explicit "SUPERSEDED" /
      "Historical note" / "**⚠️**" block OR inside §2 of
      `contracts/messaging-gateway-payload.md` (the legacy-path
      section is bit-for-bit preserved per FR-020 and intentionally
      retains the legacy `msg.template = {name, locale, variables}`
      shape — that is NOT what this gate watches for; the gate
      watches for `template` / `body` / wire-locale on the Direct
      Send path specifically). The legacy §2.x `msg.template` and
      `msg.body`-equivalent references are exempt. Cross-check the
      canonical sibling-key presence: run
      `rg -n 'msg\.direct_send_template_name|msg\.text' specs/002-direct-send-broadcasts/`
      and confirm each operator-facing artefact (`quickstart.md`,
      `research.md`, `data-model.md`, `contracts/`) references the
      new canonical wire keys at least once in the Direct Send
      sections per FR-014c(g) / FR-014d(b). The
      `Template.metadata["body"]` storage key in `data-model.md §3`
      is UNTOUCHED by FR-014d (wire-only rename per FR-014d(c)) —
      a `data-model.md §3` reference to `metadata.body` is
      intentional and is NOT a survivor for this gate; only wire
      `msg.body` references are caught.

**Checkpoint**: Live model + tests are aligned with `data-model.md §1` (`direct_send` lives inside `IntegratedAgent.config` JSON; no model column). Phase 4 (US2) can now be authored against the canonical storage shape from the start.

---

## Phase 4: User Story 2 — Onboard an OrderStatus agent without creating templates in Meta (Priority: P2)

**Goal**: When the operator assigns the OrderStatus agent to a project whose WhatsApp channel reports Direct Send enabled, persist all OrderStatus templates locally with content fetched from Meta's library catalog (in the project's resolved language, with per-template `pt_BR` fallback), set `IntegratedAgent.direct_send=True`, and skip every Meta / Integrations template-creation submission. The whole flow stays inside the existing `@transaction.atomic` and fails atomically if any required template is unavailable in both languages.

**Independent Test**: Configure a project whose `App.config.direct_send=True` (mocked at `IntegrationsService.get_channel_app`) and assign the OrderStatus agent. Verify zero calls to `notify_integrations` / `IntegrationsService.fetch_templates_from_user`, every persisted Template carries body / header / footer / buttons in the project's language (or `pt_BR` with a logged warning per fallback), every Version is `status="APPROVED"`, and `IntegratedAgent.config["direct_send"] is True` (per Phase 3.5's canonical JSON-key storage — `data-model.md §1`). **Storage-key invariant (FR-014d(c) — wire-only rename)**: assignment-time persistence MUST write Meta's `body` field to `Template.metadata["body"]` — NOT `Template.metadata["text"]`. The FR-014d wire-key rename (`msg.body` → `msg.text`) applies EXCLUSIVELY to the outbound Flows payload; the internal storage key on `Template.metadata` is preserved as `body` for log-consumer stability and migration-cost avoidance. T117(f) pins this invariant explicitly.

### Tests for User Story 2 (TDD — write FIRST, ensure FAIL before implementation)

- [X] T015 [P] [US2] Tests for `MetaClient.fetch_library_template_by_name_and_language` in `retail/clients/meta/tests/test_meta_client.py` covering: HTTP success returns the exact-name + exact-language match when Meta returns multiple fuzzy hits (contracts/meta-library-catalog.md §3); HTTP success with no exact-name match returns `None`; HTTP success with an exact-name match but a different `language` field — the cross-language false-positive scenario (Meta returns the `pt_BR` variant of the template when `es_MX` was requested but missing) — returns `None` so the use case can correctly trigger the `pt_BR` fallback path; HTTP success with empty `data` returns `None`; HTTP success with a response item that omits the `language` field is accepted as a name-match (contract §3 makes the language guard conditional on the field's presence); HTTP failure (mock `make_request` to raise `CustomAPIException`) propagates the exception (the service layer is responsible for swallowing it).
- [X] T016 [P] [US2] Tests for `MetaService.fetch_library_template_by_name_and_language` in `retail/services/meta/tests/test_meta_service.py` covering: passthrough on client success; returns `None` on `CustomAPIException` with an `error` log including `template_name` and `language`; returns `None` and logs `error` when the client returns a payload whose shape `TemplateTranslationAdapter` rejects (mock the adapter to raise; matches `contracts/meta-library-catalog.md §4` "malformed JSON / unexpected schema" failure mode).
- [X] T017 [P] [US2] Tests for `_meta_library_template_fetch.py` helpers in `retail/templates/tests/usecases/test_meta_library_template_fetch.py`:
  - For the pure adapter `adapt_meta_library_template_response` (T023(a)): returns the local-`Template.metadata` shape (`header`/`body`/`body_params`/`footer`/`buttons`/`category`/`language`) for a typical OrderStatus template; returns `None` when `raw is None`; raises `DirectSendUnsupportedComponentError` when the raw response carries (i) an unsupported top-level **component type** (carousel, list, catalog), (ii) an unsupported **button.type** value — at v1 the surface checked here is the catch-all "any value other than `URL` or `QUICK_REPLY`" (the FR-003f-specific per-type rejection cases — `PHONE_NUMBER`, `PAYMENT_REQUEST`, `ORDER_DETAILS`, `COPY_CODE`, `FLOW` — are pinned by Phase 8 / T109), (iii) more than one `URL` button or more than three `QUICK_REPLY` buttons, (iv) any pre-substitution component exceeding Meta's documented length limits — body > 1024, header.text > 60, footer > 60, button text > 20 chars, or (v) a malformed / missing-key payload that the adapter cannot decode (`contracts/meta-library-catalog.md §4` — "malformed JSON / unexpected schema"). **Taxonomy note (Session 2026-05-22 / FR-003f)**: Meta's API uses the label `ORDER_DETAILS` for a BUTTON type (the order-details payment surface) and the label `FLOW` for a BUTTON type (Flow messages); both are NOT top-level component types. An earlier version of this task listed `order_details` and `flow_message` under (i); they have been relocated to (ii) so the taxonomy matches the upstream contract. The full per-type rejection coverage for FR-003f lives in Phase 8 / T109.
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
- [X] T024 [US2] Refactor `ValidatePreApprovedTemplatesUseCase._get_template_info` in `retail/agents/domains/agent_management/usecases/validate_templates.py` to keep calling `meta_service.get_pre_approved_template(name, language)` (fuzzy semantics preserved per research Decision 4) and delegate ONLY the response-shaping step to `adapt_meta_library_template_response` from T023(a). Behavior must remain identical for the legacy push-time validation — same HTTP call, same first-hit selection, same `TemplateInfo` output shape; existing tests of `_get_template_info` must keep passing without modification (research Decision 9). **⚠️ Test deviation (aligns with FR-003e — Session 2026-05-22)**: existing `test_validate_pre_approved_templates.py` was updated minimally — the `template_adapter` constructor kwarg was removed (the adapter is now encapsulated in `_meta_library_template_fetch.py`) and the `metadata.header` assertion changed from `{"type": "TEXT", "text": "..."}` (mocked legacy transformer return) to `{"header_type": "TEXT", "text": "..."}` (the canonical Retail-internal shape consumed by `Broadcast.build_broadcast_template_message` at `broadcast.py:100` `header["header_type"]` AND by `Broadcast.build_direct_send_message`, and pinned as canonical by spec FR-003e + `data-model.md §3` "`header` canonical shape"). The legacy code's mocked-only path was producing the wrong key (`type` vs `header_type`); this is a latent-bug fix, not a behavior regression — see `data-model.md §3` for the canonical metadata shape. FR-003e's normative effect on the FETCH path (Direct Send branch) is covered by Phase 8 / T108.
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

> ## ⚠️ Phase 7 re-run gate (pinned 2026-05-22 by `/speckit-analyze` — now covers BOTH Phase 8 extensions)
>
> The Phase 7 checkmarks below reflect the state at the close of the
> ORIGINAL Phase 7 pass (before FR-003g / FR-014a / FR-014b / FR-014c /
> FR-014d were appended to `spec.md`). After **each Phase 8 extension**
> lands — the first extension (T112 / T113 / T114 / T115) AND the
> second extension (T116 / T117 / T118) — **T036 + T037 + T038 + T039
> MUST be re-run / re-verified** before merge:
>
> - **T036** — re-run the `quickstart.md` validation script against a
>   fixture whose Direct Send dispatch covers the union of all five
>   wire-shape rules (FR-014a + FR-014b + FR-014c + FR-014d): the
>   captured Flows POST body MUST carry (a) `msg.interaction_type =
>   "cta_url"` + `msg.cta_message = {display_text, url}` (FR-014a),
>   (b) `msg.quick_replies = [...]` (FR-014b) when QUICK_REPLY entries
>   are present, (c) NO `msg.buttons` key on the Direct Send path
>   (combined FR-014a / FR-014b LEGACY-ONLY rule), (d) NO `msg.template`
>   key + `msg.direct_send_template_name == "<Version.template_name>"`
>   (FR-014c), (e) NO `msg.locale` / `msg.language` keys (FR-014c(f)),
>   (f) NO `msg.body` key + `msg.text == "<substituted body>"`
>   (FR-014d). Use a fixture template that exercises both extensions
>   (`metadata.buttons` includes BOTH a URL and at least one
>   QUICK_REPLY) plus a non-default locale (e.g. `es_MX`) so the
>   FR-014c(f) wire-locale-drop rule is exercised end-to-end.
> - **T037** — re-run `poetry run coverage run manage.py test &&
>   poetry run python contrib/compare_coverage.py` AFTER T112–T114
>   land AND AGAIN after T116 / T117 land. The compare script MUST
>   NOT report `Number of test lines decreased`; T011a's
>   `[~] SUPERSEDED by T114` removal of the old QUICK_REPLY assertions
>   is offset by T114's new-shape assertions plus T112 / T113's new
>   branches; T116 / T117 introduce net-new test methods on the
>   FR-014c / FR-014d surface (no `[~] SUPERSEDED` offset on the
>   second extension), so the second-extension net delta is strictly
>   positive.
> - **T038** — re-run pre-commit on the additional files touched by
>   T112 / T113 / T114 (the override map module, `broadcast.py`,
>   `direct_send_payload_builder.py`, and the matching test files),
>   AND on the additional files touched by T116 / T117 (`broadcast.py`,
>   `test_broadcast_direct_send.py`).
> - **T039** — update the open PR's `## Backward-compatibility &
>   untestable-by-design checklist gate` section to explicitly cite
>   the FR-003g / FR-014a / FR-014b coverage delivered by the Phase 8
>   first extension AND the FR-014c / FR-014d coverage delivered by
>   the Phase 8 second extension; re-cite the file diffs that
>   demonstrate compliance
>   (`retail/agents/domains/agent_webhook/services/broadcast.py`,
>   `retail/agents/domains/agent_webhook/services/direct_send_payload_builder.py`,
>   `retail/templates/usecases/_meta_library_template_fetch.py`,
>   the override-map module hosting `DIRECT_SEND_BUTTON_LABEL_OVERRIDES`,
>   and `contracts/messaging-gateway-payload.md`).
>
> The original `[X]` markers below are preserved verbatim for
> git-history continuity, but Phase 7 is NOT closed for merge until
> the four re-run items above complete for BOTH Phase 8 extensions.
> The OUTSTANDING WORK BEFORE MERGE banner at the top of this file
> is the single canonical place that lists what blocks merge.

- [X] T036 [P] Run the `quickstart.md` validation script step-by-step in a local environment with a Direct Send-enabled fixture (see `quickstart.md §0 Prerequisites` for the fixture composition — OrderStatus agent pushed, WhatsApp Cloud channel created via onboarding, channel opted into Direct Send Beta with `App.config.direct_send=True`, project's VTEX tenant has a resolvable `defaultLocale`, `settings.ORDER_STATUS_AGENT_UUID` set, Meta library catalog has the OrderStatus templates available in the project's locale or `pt_BR`) and confirm every "Expected outcome" matches. **⚠️ Phase 7 re-run gate**: re-run after T113 / T114 land against a fixture that includes BOTH a CTA URL and at least one QUICK_REPLY button (combined-case per FR-014b(f)) and confirm the captured Flows POST body carries `msg.interaction_type` / `msg.cta_message` / `msg.quick_replies` and NO `msg.buttons` key.
- [X] T037 Run `poetry run coverage run manage.py test && poetry run coverage report -m | tee /tmp/feature_coverage.txt` and then `poetry run python contrib/compare_coverage.py`. The compare script MUST NOT report `Number of test lines decreased`; if it does, add the missing tests in the same PR (Constitution Principle III — NON-NEGOTIABLE). **⚠️ Phase 7 re-run gate**: re-run AFTER T112 + T113 + T114 land. Without this re-run, T011a's `[~]` removal of the original QUICK_REPLY assertions is not offset by T114's replacements in the coverage floor and the merge gate is structurally satisfied only on paper.
- [X] T038 [P] Run pre-commit on every changed file: `poetry run pre-commit run --files <changed-files>`. Black + flake8 must pass clean. **⚠️ Phase 7 re-run gate**: re-run on the additional files touched by T112 / T113 / T114 once they land.
- [X] T039 Open the PR with title `feat: add WhatsApp Direct Send dispatch path for OrderStatus` (≤72 chars) and a body following the `## What` / `## Why` template (Constitution Principle V). **⚠️ Phase 7 re-run gate**: when T112 / T113 / T114 land, update the PR body's `## Backward-compatibility & untestable-by-design checklist gate` section to also confirm that FR-003g / FR-014a / FR-014b are now covered by the listed file diffs (override-map module, `broadcast.py`, `direct_send_payload_builder.py`, `_meta_library_template_fetch.py`). Branch name: `002-direct-send-broadcasts` (already provided by `/speckit-plan`). Reference the spec, plan and research files in the body. The PR body MUST also include a **`## Backward-compatibility & untestable-by-design checklist gate`** section that explicitly confirms the SIX requirements `plan.md` §Complexity Tracking documents as having no automated test — three "thou shalt not" backward-compat requirements (FR-022 / FR-023 / FR-024), the Celery one-shot stance (FR-038), the inbound EDA tenant-resolution restatement (FR-041), and the FR-043 v1 deferral — were reviewed against `checklists/backward-compatibility.md` (CHK013–CHK022, CHK027–CHK029), `checklists/idempotency.md` (CHK014), and `checklists/tenant-isolation.md` (CHK022–CHK025, CHK044) and remain satisfied: (i) FR-022 — no required field was added to any inbound payload (order-status webhook, agent-assignment, send-test-template, template-status webhook); no URL path, HTTP method, required header, or required query parameter was renamed or removed; (ii) FR-023 — the template-status webhook handler is untouched (no new Integrations Engine subscription, no signature change, no downstream side-effect change); (iii) FR-024 — no new environment variable or settings key was introduced (deploying the feature without any settings change is safe); (iv) FR-038 — `retail/celery.py` diff is empty for retry-related keys (no `task_acks_late=True` override, no `task_default_retry_delay` change, no broker DLX configuration added) AND the three OrderStatus-pipeline tasks (`task_order_status_update`, `task_mark_broadcast_converted`, `handle_purchase_event_task`) carry no new `bind=True` / `retry_kwargs={...}` decorators / `self.retry(...)` calls; (v) FR-041 — no inbound EDA consumer (`BroadcastSendConsumer` on `retail.template-send`, `BroadcastStatusConsumer` on `retail.template-status`, the order-status webhook entry point at `retail/agents/domains/agent_webhook/usecases/order_status.py`) was modified by this PR; tenant-resolution mechanisms (a)–(d) remain unchanged and are covered transitively by T035c; (vi) FR-043 — the explicit Retail-side cross-validation (`app.config.project_uuid == request.headers["Project-Uuid"]` with HTTP 403 on mismatch) is NOT implemented in this PR by design; the trust boundary on Integrations Engine + DRF `HasProjectPermission` + `IntegrationsService.get_channel_app(...)` fail-closed `None` is the v1 enforcement gate, with the explicit cross-validation deferred to a separate `feat/tenant-isolation-cross-validation` PR. Each line above MUST cite the file diff that demonstrates compliance (e.g. "`retail/settings.py` diff is empty for new keys", "`retail/celery.py` diff is empty", "`retail/broadcasts/consumers/` diff is empty for tenant-resolution logic") so reviewers can verify in one read.

---

## Phase 8: Post-implementation fold-in — Session 2026-05-22 spec clarifications

**Purpose**: Cover the **eight** normative clarifications added to
`spec.md` AFTER Phase 7 closed out. Three were folded in on
2026-05-22 (the original Phase 8 scope), three more were appended
later in the same session and are folded in by the Phase 8 first
extension introduced 2026-05-22, and two were appended at the tail
of the same session (FR-014c / FR-014d wire-shape breaks) and are
folded in by the Phase 8 second extension pinned 2026-05-22 by
`/speckit-analyze`:

- **Original Phase 8 scope (T107–T111, T120)** — adapter rules:
  - **FR-003e** — `header` plain-string + canonical normalization.
  - **FR-003f** — button-type strict rejection + dual URL-button shape normalization.
  - **Session 2026-05-22 Q3** — drop-rule for auxiliary curation fields.

  All three use the pre-existing
  `DirectSendUnsupportedComponentError` exception (T007) so no new
  exception type is introduced.

- **Phase 8 first extension (T112–T115)** — adapter override map +
  dispatch-time wire-shape relocation + contract correction:
  - **FR-003g** — per-`(template_name, language)` button-label
    override map (Session 2026-05-22 Q5–Q9).
  - **FR-014a** — CTA URL wire shape relocated from
    `msg.buttons[*].sub_type="cta_url"` to top-level
    `msg.interaction_type="cta_url"` + `msg.cta_message={display_text, url}`
    (Session 2026-05-22 Q4).
  - **FR-014b** — QUICK_REPLY wire shape relocated from
    `msg.buttons[*].sub_type="reply"` to flat
    `msg.quick_replies=["title 1", ...]` array (Session 2026-05-22
    Q10). Combined with FR-014a, the Direct Send path NEVER emits
    `msg.buttons` (LEGACY-ONLY).
  - Contract artifact correction (`contracts/messaging-gateway-payload.md`
    §3.1 / §3.3 / §3.4 / §4 / §5.1) tracked as T115 per
    FR-014a(f) / FR-014b(g) (mirroring FR-003e's `header` precedent).

  FR-003g re-uses
  `DirectSendUnsupportedComponentError(component_type="buttons")`
  for FR-003g(h) "override value still overflows"; FR-014a / FR-014b
  are wire-shape relocations of pre-existing fields and require no
  new exception type either.

- **Phase 8 second extension (T116–T118)** — wire-shape breaks +
  contract correction (pinned 2026-05-22 by `/speckit-analyze`):
  - **FR-014c** — drop `msg.template` from the Direct Send payload
    entirely; emit the local template name on the top-level sibling
    key `msg.direct_send_template_name`; drop locale from the wire
    (no `msg.locale` / `msg.language`). Combined with FR-014a /
    FR-014b, the Direct Send `msg` is now a top-level-keys-only
    structure with NO nested `template` / `buttons` sub-objects
    (Session 2026-05-22 Q14 / Q15 / Q17).
  - **FR-014d** — rename the wire body key from `msg.body` to
    `msg.text` on the Direct Send path. **Wire-only rename**:
    `Template.metadata["body"]`, the `MAX_BODY_LENGTH` constant,
    the FR-039 `reason=empty_body` audit-log discriminator, and
    the local variable identifiers are preserved unchanged
    (Session 2026-05-22 Q16 / Q18).
  - Contract artifact correction (`contracts/messaging-gateway-payload.md`
    §3.1 / §3.3 / §3.4 / §5.1 / §5.1b / §5.1c / §5.2) tracked as
    T118 per FR-014c(c) / FR-014d(g) (mirroring T115's precedent).

  Neither FR-014c nor FR-014d introduces a new exception type —
  both are pure wire-shape changes; FR-017's naming-rule gate
  (`is_valid_direct_send_template_name`) is preserved (the validated
  name now flows into `msg.direct_send_template_name` instead of
  `msg.template.name`); the FR-039 audit-log shapes are preserved
  bit-for-bit (the audit log is INTERNAL observability and is NOT
  affected by the wire-shape rename per FR-014c(d) / FR-014d(c)).

See `plan.md` Constraints sub-section "Post-design spec updates
folded in" and `data-model.md §5` "Adapter normative behaviour" for
the canonical restatements.

> **Task numbering**: Phase 8 uses T107–T111 for the original
> TDD-first tests, T120 for the original implementation task,
> T112–T115 for the Phase 8 first extension (FR-003g / FR-014a /
> FR-014b tests + adapter & dispatch implementation + contract
> correction), and T116–T118 for the Phase 8 second extension
> (FR-014c / FR-014d tests + dispatch implementation + contract
> correction). T119 is intentionally reserved (unused) so a future
> incremental fold-in can fit between T118 and T120 without
> renumbering existing tasks.

> **Execution order**: Phase 8 runs AFTER Phase 7 (which is already
> `[X]`). The Phase 8 tests MUST be authored TDD-first (red against
> the current adapter / dispatch builder), then the adapter
> (`retail/templates/usecases/_meta_library_template_fetch.py`) and
> the dispatch builder
> (`retail/agents/domains/agent_webhook/services/broadcast.py` +
> `direct_send_payload_builder.py`) are tightened to make them
> green. If any of the rules is already satisfied by the current
> implementation the matching test passes on first run — that is
> the desired outcome, not a reason to skip the task; the test pins
> the rule against future regressions. **Within the Phase 8 first
> extension** the recommended single-PR order is **T112 (FR-003g
> tests + adapter override map) → T113 (FR-014a CTA URL wire shape
> tests + dispatch builder) → T114 (FR-014b quick_replies wire
> shape tests + dispatch builder) → T115 (contract correction)** so
> dispatch-side tests are red against the same code that the
> dispatch-builder commit will make green and the contract artefact
> is corrected last (the contract follows the spec, not vice versa
> — same precedent as FR-003e). **Within the Phase 8 second
> extension** the recommended single-PR order is **T116 (FR-014c
> tests + dispatch builder — drop `msg.template`, add
> `msg.direct_send_template_name`) → T117 (FR-014d tests +
> dispatch builder — rename `msg.body` → `msg.text`) → T118
> (contract correction)** for the same reason; T116 and T117 touch
> overlapping lines in `Broadcast.build_direct_send_message`
> (`broadcast.py:804-822`) so authoring them in this order keeps
> each commit's diff scoped to a single FR.

> **Coverage parity (Phase 7 / T037)**: any new branch added to the
> adapter or the dispatch builder to satisfy Phase 8 MUST come with
> the matching test in the same PR (Constitution Principle III —
> NON-NEGOTIABLE). Rerun `poetry run python contrib/compare_coverage.py`
> after Phase 8 and confirm `Number of test lines decreased` is NOT
> reported. T011a's `[~] SUPERSEDED by T114` marker means the
> original quick-reply shape assertions are dropped from the
> coverage floor; T114 introduces the canonical-shape assertions on
> the same code paths plus the new flat-array assertions, so the
> net coverage delta is positive. T116 / T117 do NOT carry `[~]`
> SUPERSEDED markers on existing tasks — they introduce net-new
> assertions (no `msg.template` key, no `msg.body` key, presence of
> `msg.direct_send_template_name`, presence of `msg.text`), so the
> second-extension delta is positive by construction.

### Tests for Phase 8 (TDD — write FIRST, ensure FAIL or PIN current behavior)

- [X] T107 [P] **Header — plain-string normalization happy path (FR-003e)** — Test in `retail/templates/tests/usecases/test_meta_library_template_fetch.py` covering: `adapt_meta_library_template_response` invoked with a raw response whose `header` is a plain text string (e.g. `"Pedido enviado"`) MUST return a `TemplateInfo` whose `metadata.header == {"header_type": "TEXT", "text": "Pedido enviado"}` — the canonical Retail-internal shape per `data-model.md §3` "`header` canonical shape". Cover one additional case where `header` is absent → `metadata.header` is absent (or `None`) accordingly. This pins FR-003e's normalization rule against a future refactor that re-introduces the pre-FR-003e dict `{type, text}` shape.
- [X] T108 [P] **Header — non-string rejection routes through FR-003c→FR-003d (FR-003e)** — Test in the same file covering: `adapt_meta_library_template_response` invoked with a raw response whose `header` is a dict (the historical `{"type": "TEXT", "text": "..."}` shape OR any other dict) MUST raise `DirectSendUnsupportedComponentError(component_type="header")` so the use case routes the exception through FR-003c (pt_BR retry) and FR-003d (atomic rollback). Capture the raised exception, assert `exc.component_type == "header"`, and assert no `metadata` is returned. **Use-case-level routing assertion (optional but preferred)**: in a sibling test method against `AssignAgentUseCase._create_library_templates` with a `MagicMock(spec=MetaService)` that returns the dict-shaped header on the first call (project locale) and a valid plain-string header on the second call (`pt_BR`), assert the FR-003c warning log fires AND the assignment ultimately succeeds with the `pt_BR` content — proving the exception is routed through the fallback, not propagated to the caller.
- [X] T109 [P] **Button — strict per-type rejection (FR-003f)** — Test in the same file covering: `adapt_meta_library_template_response` invoked with a raw response whose `buttons[*].type` equals one of `PHONE_NUMBER`, `PAYMENT_REQUEST`, `ORDER_DETAILS`, `COPY_CODE`, `FLOW` MUST raise `DirectSendUnsupportedComponentError(component_type=<type>)` for EACH type (one test method per type, OR a parametrised test with one assertion per type). Pin the per-type coverage explicitly so a future refactor that adds a generic "not in allow-list" branch (which would already pass T017's case (ii)) is observable as the intended FR-003f rule rather than as a coincidence. Cover one positive case: a `URL` and a `QUICK_REPLY` button in the same template both succeed (the rejection is type-specific, not blanket).
- [X] T110 [P] **Button — dual URL shape normalization (FR-003f)** — Test in the same file covering: `adapt_meta_library_template_response` invoked with a raw `URL` button in EACH of the two upstream shapes — (a) flat `{"type": "URL", "text": "Track", "url": "https://loja.com/track/{{1}}"}` and (b) legacy nested `{"type": "URL", "text": "Track", "url": {"base_url": "https://loja.com/track/", "url_suffix_example": "{{1}}"}}` — MUST produce a `TemplateInfo` whose `metadata.buttons[0]["url"]` is the SAME flat string (`"https://loja.com/track/{{1}}"`) in both cases. The normalization MUST go through the same `_ensure_protocol` + `_append_placeholder_if_needed` heuristic the push-path `ButtonTransformer` already applies, so a `base_url` missing the scheme (e.g. `"loja.com/track/"`) survives the same protocol-prepend logic. Pin one case where the URL has a substitutable placeholder (`{{1}}`) to confirm placeholders are preserved verbatim through the normalization (they're substituted later by `Broadcast.build_direct_send_message`).
- [X] T111 [P] **Auxiliary curation field drop (Session 2026-05-22 Q3)** — Test in the same file covering: `adapt_meta_library_template_response` invoked with a raw response that carries the auxiliary fields `body_param_types`, `attributes`, `topic`, `usecase`, `industry`, `id` (each at the top level of the raw template payload) MUST produce a `TemplateInfo` whose `metadata` does NOT contain ANY of those keys. Allowed keys are the dispatch-relevant subset `{header, body, body_params, footer, buttons, category, language}` — assert each forbidden key is absent via `self.assertNotIn(key, info["metadata"])` (one assertion per key for diagnostics). The `direct_send` audit sub-object is added by `AssignAgentUseCase._create_library_templates` at write time (not by the adapter), so this test MUST NOT expect it on the adapter's return shape.

  **Positive subset-preservation assertion (pinned 2026-05-22 by `/speckit-analyze`)**: in addition to the negative `assertNotIn` assertions above, the SAME test MUST positively assert that every dispatch-relevant key actually present in the raw response survives the drop pass — for the canonical OrderStatus fixture (body + body_params + optional header + optional footer + optional buttons + category + language), assert `self.assertIn(key, info["metadata"])` for each of `body`, `body_params`, `category`, `language`, AND assert `self.assertIn(key, info["metadata"])` for `header` / `footer` / `buttons` IFF the raw response carries them. Without this positive branch, a regression that drops `body_params` together with `body_param_types` (the field name collision is a realistic failure mode for a future adapter refactor) would pass the negative-only assertions and silently break Direct Send dispatch — `Broadcast.build_direct_send_message`'s variable substitution path reads `metadata["body_params"]` (or its successor) to map positional placeholders.

### Tests + implementation for Phase 8 extension (FR-003g / FR-014a / FR-014b — TDD-first)

> **Pattern**: each task pairs the TDD-first tests AND the
> implementation contract for the rule it covers, so the Phase 8
> extension can be reviewed rule-by-rule without splitting code and
> tests across separate PRs (matching the Phase 8 original style of
> T120 holding the implementation contract for T107–T111). Tests
> MUST be observed to FAIL before the matching implementation is
> commited (Constitution Principle III + project SKILL).

- [X] T112 [P] [US2] **FR-003g — per-`(template_name, language)` button-label override map (Session 2026-05-22 Q5–Q9)** — Tests in `retail/templates/tests/usecases/test_meta_library_template_fetch.py` AND adapter implementation in `retail/templates/usecases/_meta_library_template_fetch.py` (or in the same module that hosts `_validate_and_normalize_buttons`). **Tests** (one method per branch):
  - **(a) Trigger — overflow + map hit**: raw response carries a `URL` button whose `text="Ver detalhes do pedido"` (22 chars, exceeds `MAX_BUTTON_LABEL_LENGTH=20`); call `adapt_meta_library_template_response(raw, language="pt_BR")` (or whatever signature the adapter exposes for receiving the language); assert returned `metadata.buttons[0]["text"] == "Detalhes do pedido"` (18 chars) AND a single `logger.info` line is emitted matching the FR-003g(f) shape `direct_send_button_label_overridden: template={template_name} language={language} upstream='{upstream}' ({n} chars) override='{override}' ({m} chars)` (capture with `assertLogs` at INFO level).
  - **(b) Trigger — overflow + map miss**: raw response carries a `URL` button whose `text="Some 21-char label …"` (>20 chars) for a `(template_name, language)` pair NOT in the map; assert `DirectSendUnsupportedComponentError(component_type="buttons")` is raised (the existing FR-003f.c failure path applies).
  - **(c) No-trigger — upstream fits**: raw response carries a `URL` button whose `text="View order details"` (18 chars, fits within 20); assert the override map is NEVER consulted (mock the map lookup with a sentinel that fails the test if invoked, OR assert the persisted `metadata.buttons[0]["text"]` is byte-identical to the upstream value); the upstream value is the persisted value verbatim. This pins FR-003g(b) "trigger conditional on overflow".
  - **(d) Override scope — URL only**: raw response carries a `QUICK_REPLY` button whose `title` exceeds 20 chars; assert `DirectSendUnsupportedComponentError(component_type="buttons")` is raised regardless of any QUICK_REPLY entries in the map (no QUICK_REPLY entry is permitted in v1 per FR-003g(d) / FR-003g(g)).
  - **(e) Misconfigured override still overflows**: monkey-patch the map to contain `("test_template", "pt_BR"): "<21-char string>"` for the duration of the test (use `unittest.mock.patch.dict` on the live constant to avoid leaking); raw response carries a matching `URL` button whose upstream `text` exceeds 20 chars; assert `DirectSendUnsupportedComponentError(component_type="buttons")` is raised. This pins FR-003g(h) "override is a remediation, not a length-check bypass".
  - **(f) Initial map content (FR-003g(g))**: assert the live map (read directly from the implementation module) contains EXACTLY the two seed entries `{("order_canceled_3", "pt_BR"): "Detalhes do pedido", ("order_canceled_3", "es"): "Detalles del pedido"}` and no other entries; this is a snapshot test against `len(DIRECT_SEND_BUTTON_LABEL_OVERRIDES) == 2` plus the two `assertEqual`s on the values. Adding any further entry without a spec amendment fails this test on the offending PR.

  **Implementation contract**: declare `DIRECT_SEND_BUTTON_LABEL_OVERRIDES: dict[tuple[str, str], str]` as a module-level constant alongside `direct_send_constants.py` (or in a sibling module imported by `_meta_library_template_fetch.py` per FR-003g(a)) with exactly the two seed entries. Inside `_validate_and_normalize_buttons`, when an entry of `type == "URL"` would otherwise fail the existing `MAX_BUTTON_LABEL_LENGTH` check, look up `(template_name, language)` in the map; on hit, replace `button["text"]` with the override value and re-run the length check (FR-003g(c) / FR-003g(h)); on miss, raise `DirectSendUnsupportedComponentError(component_type="buttons")` per the existing FR-003f.c failure path. Emit `logger.info` at the override site per FR-003g(f). NO branch on `template_name` outside the map lookup is permitted (FR-003g(a)). NO entry is added to `Template.metadata.direct_send` to record that the override fired (FR-003g(f) — log-only audit). The `template_name` and `language` arguments threaded into `_validate_and_normalize_buttons` come from the same call site that decides which `language` the fetch is occurring in (project locale vs `pt_BR` fallback in `AssignAgentUseCase._create_library_templates`); if the existing adapter signature does not currently surface them, extend the signature additively.

- [X] T113 [US1] **FR-014a — CTA URL wire shape relocation (Session 2026-05-22 Q4)** — Tests in `retail/agents/tests/services/test_broadcast_direct_send.py` AND `retail/agents/tests/services/test_direct_send_payload_builder.py` AND dispatch implementation in `retail/agents/domains/agent_webhook/services/broadcast.py` + `retail/agents/domains/agent_webhook/services/direct_send_payload_builder.py`. **Tests** (one method per branch):
  - **(a) Wire shape — URL only**: a Direct Send-enabled IntegratedAgent + a Template whose `metadata.buttons` has exactly one `{type: "URL", text: "Acompanhar pedido", url: "https://loja.com/track/{{1}}"}` entry; call `Broadcast.build_direct_send_message(...)` with `template_variables={"1": "12345"}`; assert the returned `msg` carries `msg["interaction_type"] == "cta_url"`, `msg["cta_message"] == {"display_text": "Acompanhar pedido", "url": "https://loja.com/track/12345"}`, AND `"buttons" not in msg` (the LEGACY-ONLY rule from FR-014b(b)).
  - **(b) Discriminator spelling**: same fixture as (a); assert the literal key `interaction_type` is present and the misspelled `interactive_type` is absent (`assertIn("interaction_type", msg); assertNotIn("interactive_type", msg)`). FR-014a(a).
  - **(c) Variable substitution on both sub-fields**: a Template whose URL button is `{type: "URL", text: "Acompanhar {{1}}", url: "https://loja.com/track/{{2}}"}` with `template_variables={"1": "Maria", "2": "12345"}`; assert `msg["cta_message"]["display_text"] == "Acompanhar Maria"` AND `msg["cta_message"]["url"] == "https://loja.com/track/12345"`. FR-014a(d).
  - **(d) Length-limit refusal — `cta_message.display_text`**: `metadata.buttons[0].text` such that the post-substitution `display_text` exceeds `MAX_BUTTON_LABEL_LENGTH` (e.g. `"{{1}} {{2}} {{3}}"` substituted to a >20-char string); assert `build_direct_send_message` returns `None` AND emits the existing audit-log shape `[BroadcastDispatch] skipped_due_to_direct_send_validation: project_uuid={...} agent={...} template={...} reason=component_length_limit event={data}`. The reason discriminator is unchanged from T013; what changes is the LOCATION the limit is read from — `_exceeds_direct_send_length_limits` MUST check `msg.cta_message.display_text` (NOT `msg.buttons[*].display_text`). FR-014a(e).
  - **(e) URL length is NOT limited**: same fixture as (a) but with a 200-char `url`; assert `build_direct_send_message` returns a non-None payload and the URL is preserved verbatim — the 20-char `MAX_BUTTON_LABEL_LENGTH` ceiling applies to `display_text` only, never to `url` (contract §3.3 / `cta_url` row).
  - **(f) Pure-helper test**: in `test_direct_send_payload_builder.py`, exercise the new helper signature directly (whichever shape the implementation chooses — e.g. `build_direct_send_cta_message(metadata, template_variables, *, template_name) -> Optional[Dict[str, Any]]`). Assert it returns `None` when no `URL` button is present, returns `{"display_text": ..., "url": ...}` when present, and is invoked at most once per dispatch (FR-014a(c) — count cap is structural via FR-003f's ≤1 URL fetch-time guard).

  **Implementation contract**: in `direct_send_payload_builder.py`, replace the URL branch of `build_direct_send_buttons` with a new top-level helper that returns the FR-014a `cta_message` dict (or extend the dispatch builder directly to consume it). In `Broadcast.build_direct_send_message`, when the substituted CTA URL helper returns a dict, set `msg["interaction_type"] = "cta_url"` and `msg["cta_message"] = {"display_text": ..., "url": ...}`; do NOT add the URL entry to `msg.buttons`. Update `_exceeds_direct_send_length_limits` (`broadcast.py:820-850`) to read the post-substitution `display_text` from `msg.get("cta_message", {}).get("display_text", "")` instead of iterating `msg["buttons"][*]`. The combined-case interaction with FR-014b is pinned by T114(g).

- [X] T114 [US1] **FR-014b — QUICK_REPLY wire shape relocation (Session 2026-05-22 Q10)** — **SUPERSEDES T011a**. Tests in `retail/agents/tests/services/test_broadcast_direct_send.py` AND `retail/agents/tests/services/test_direct_send_payload_builder.py` AND dispatch implementation in `retail/agents/domains/agent_webhook/services/broadcast.py` + `retail/agents/domains/agent_webhook/services/direct_send_payload_builder.py`. **Tests** (one method per branch):
  - **(a) Wire shape — flat array of titles**: a Direct Send-enabled IntegratedAgent + a Template whose `metadata.buttons` carries 3 `QUICK_REPLY` entries with `text` of "Sim" / "Não" / "Cancelar"; call `Broadcast.build_direct_send_message(...)`; assert `msg["quick_replies"] == ["Sim", "Não", "Cancelar"]` (a JSON list of strings, no wrapping object) AND `"buttons" not in msg`. FR-014b(a) / FR-014b(b).
  - **(b) Order preservation**: same fixture; assert the order of titles in `msg["quick_replies"]` matches the order of entries in `metadata.buttons` (this is the regression-pin equivalent of T011a's "preserves order" assertion, lifted onto the new shape).
  - **(c) `id` field is intentionally not on the wire**: `metadata.buttons` carries `{type: "QUICK_REPLY", id: "yes_track", text: "Acompanhar"}`; assert each element of `msg["quick_replies"]` is a STRING (not a dict) — `assertTrue(all(isinstance(elem, str) for elem in msg["quick_replies"]))`. FR-014b(a).
  - **(d) Variable substitution applies defensively**: at least one QUICK_REPLY's `text` contains `{{1}}` (e.g. `"Acompanhar {{1}}"`) with `template_variables={"1": "12345"}`; assert the substituted value (`"Acompanhar 12345"`) appears in `msg["quick_replies"]` — even though OrderStatus titles are static today, the substitution path MUST run unconditionally per FR-014b(d).
  - **(e) Length-limit refusal — `quick_replies[*]`**: at least one `QUICK_REPLY.title` such that the post-substitution title exceeds `MAX_BUTTON_LABEL_LENGTH=20`; assert `build_direct_send_message` returns `None` + the existing `reason=component_length_limit` audit-log shape (same as T013, location relocated). `_exceeds_direct_send_length_limits` MUST iterate `msg.get("quick_replies", [])` (a list of strings) instead of `msg["buttons"][*]["title"]`. FR-014b(e).
  - **(f) Combined-case (URL + ≤3 QUICK_REPLY)**: a Template whose `metadata.buttons` carries ONE `URL` entry AND TWO `QUICK_REPLY` entries; assert the resulting `msg` carries BOTH `msg["interaction_type"] == "cta_url"` + `msg["cta_message"] == {...}` (FR-014a) AND `msg["quick_replies"] == [...]` (FR-014b) as PARALLEL siblings; neither suppresses the other. FR-014b(f). This is the missing combined-case regression guard called out by `/speckit-analyze` finding M1.
  - **(g) `interaction_type` is NOT set when only QUICK_REPLY is present**: a Template whose `metadata.buttons` carries ONLY QUICK_REPLY entries (no URL); assert `"interaction_type" not in msg` AND `"cta_message" not in msg` AND `msg["quick_replies"] == [...]`. FR-014b(f) negative branch.
  - **(h) Pure-helper test**: in `test_direct_send_payload_builder.py`, exercise the new helper signature (e.g. `build_direct_send_quick_replies(metadata, template_variables, *, template_name) -> Optional[List[str]]`); assert it returns `None` when no QUICK_REPLY is present, returns a list of substituted strings when present, and the list length is ≤3 (FR-014b(c) — count cap is structural via FR-003f's ≤3 QUICK_REPLY fetch-time guard).

  **Implementation contract**: in `direct_send_payload_builder.py`, replace the QUICK_REPLY branch of `build_direct_send_buttons` with a new helper returning `Optional[List[str]]` of substituted titles (or remove the joint helper entirely and let `build_direct_send_message` compose CTA URL + quick_replies directly); the canonical decision is "the Direct Send path NEVER emits a `msg.buttons` key". In `Broadcast.build_direct_send_message`, when the QUICK_REPLY helper returns a non-empty list, set `msg["quick_replies"] = [...]`. Update `_exceeds_direct_send_length_limits` (`broadcast.py:820-850`) to iterate `msg.get("quick_replies", [])` for the per-entry post-substitution length check. After this task lands, reading `msg["buttons"]` on a Direct Send payload MUST always raise `KeyError` — pin this in (a) via `self.assertNotIn("buttons", msg)`.

- [X] T115 [docs] **Contract artifact correction (FR-014a(f) / FR-014b(g))** — Edit `contracts/messaging-gateway-payload.md` to reflect the FR-014a + FR-014b wire shapes. **Status (verified 2026-05-22 by `/speckit-analyze`)**: §3.1 / §3.2 / §3.3 / §3.4 / §3.5 / §4 / §5.1 are on disk in the canonical FR-014a / FR-014b shape (`msg.interaction_type`, `msg.cta_message`, `msg.quick_replies` siblings; the contract explicitly states "Direct Send NEVER emits `msg.buttons`"). The verification grep gate at the bottom of this task body returns zero matches inside §3.x / §5.x for `sub_type":\s*"cta_url"` and `sub_type":\s*"reply"`. Specifically: (a) §3.1 — replace the line `"buttons": [ /* see §3.3 */ ],` inside the Direct Send `msg` example with `"interaction_type": "cta_url",` (optional) + `"cta_message": { /* see §3.3 */ },` (optional) + `"quick_replies": [ /* see §3.3 */ ],` (optional); update the §3.1 table accordingly so `interaction_type` / `cta_message` / `quick_replies` rows replace the `buttons` row, and the new rows reference §3.3. (b) §3.3 — rewrite the entire "Buttons (Direct Send)" sub-section as "CTA URL and Quick Replies (Direct Send)" with the FR-014a / FR-014b shapes (cite FR-014a(c) / FR-014b(c) for the count caps, cite FR-014a(d) / FR-014b(d) for the substitution rule, cite FR-014a(e) / FR-014b(e) for the length checks); explicitly state that `msg.buttons` is LEGACY-ONLY on the Direct Send path. (c) §3.4 — update the "Behavioural guarantees" bullet that lists substitution targets to read `body`, `header.text`, `footer`, `cta_message.display_text`, `cta_message.url`, `quick_replies[*]` (drop the `buttons[*].url` / `buttons[*].title` enumeration). (d) §4 — update the validation summary's component-length-limit clause (rule 3) to read "the substituted body, header, footer, `cta_message.display_text`, or any `quick_replies[*]` …" (drop `buttons[*].title` / `buttons[*].display_text`). (e) §5.1 — replace the `"buttons": [{"sub_type": "cta_url", ...}]` array in the example with the `"interaction_type": "cta_url"` + `"cta_message": {...}` siblings on `msg`; add a sibling §5.1b example for QUICK_REPLY emitting `"quick_replies": [...]`. (f) Add a new sub-section "§3.5 — Spec is canonical" stating that this contract restates the spec-level FR-014a / FR-014b shapes for reviewer convenience and that any future drift between this contract and `spec.md` resolves in favour of the spec (mirroring the FR-003e precedent).

  **Verification (single-pass grep gate)**: after the edits, run `rg -n 'sub_type":\s*"cta_url"|sub_type":\s*"reply"' contracts/messaging-gateway-payload.md` — the command MUST return zero matches inside §3.x and §5.x. The legacy §2.2 buttons table (`sub_type: "url"`, `sub_type: "payment_request"`) is UNTOUCHED — those are the legacy-path shapes preserved bit-for-bit per FR-020. Also re-grep the contract for `buttons[*].title|buttons[*].url|buttons[*].display_text` (treated as ripgrep regex) and confirm those references are confined to §2 (legacy) and the new §3.4 reference to LEGACY-ONLY in §2; any survivor in §3.x is a residual error.

  **⚠️ Grep-gate extension — Phase 8 second extension (pinned 2026-05-22 by `/speckit-analyze`)**: when the Phase 8 second extension (T116 / T117 / T118) lands, this gate MUST be extended to also catch residual FR-014c / FR-014d wire-shape references inside Direct Send §3.x / §5.x. The canonical full gate lives on **T118**; T115's gate is augmented in lockstep so a residual `msg.template` / `msg.body` in §3.x / §5.x fails CI even if reviewers approach the contract from the first-extension verification recipe:

  ```bash
  rg -n '"template":\s*\{|"body":\s*"|msg\.template\.name|msg\.template\.locale|msg\.body' \
    specs/002-direct-send-broadcasts/contracts/messaging-gateway-payload.md
  ```

  Every match MUST land inside §2.x (legacy path, bit-for-bit preserved per FR-020) OR inside an explicit "SUPERSEDED" / "Historical note" / "**⚠️**" block. Any survivor inside §3.x / §5.x is a residual error. The legacy §2.1 `msg.template = {name, locale, variables}` example is UNTOUCHED — that is the legacy-path shape the gate intentionally allows in §2.x. See T118 for the canonical full gate (which also re-checks the FR-014a / FR-014b survivors above).

### Tests + implementation for Phase 8 second extension (FR-014c / FR-014d — TDD-first)

> **Pattern**: each task pairs the TDD-first tests AND the
> implementation contract for the rule it covers, matching the
> Phase 8 first extension precedent (T112 / T113 / T114). Tests
> MUST be observed to FAIL before the matching implementation is
> committed (Constitution Principle III + project SKILL). T116 and
> T117 touch overlapping lines in
> `Broadcast.build_direct_send_message`
> (`retail/agents/domains/agent_webhook/services/broadcast.py:804-822`)
> — author them in T116 → T117 order so each commit's diff stays
> scoped to a single FR.

- [X] T116 [US1] **FR-014c — drop `msg.template`, add `msg.direct_send_template_name`, drop wire locale (Session 2026-05-22 Q14 / Q15 / Q17)** — Tests in `retail/agents/tests/services/test_broadcast_direct_send.py` AND dispatch implementation in `retail/agents/domains/agent_webhook/services/broadcast.py`. **Tests** (one method per branch):
  - **(a) `msg.template` is dropped**: a Direct Send-enabled IntegratedAgent + a valid Template; call `Broadcast.build_direct_send_message(...)`; assert `"template" not in msg`. FR-014c(a) — the previously-implemented `msg["template"] = {"name": template_name}` emission (live at `broadcast.py:807`) is forbidden on the Direct Send path.
  - **(b) `msg.direct_send_template_name` carries the local template name**: same fixture; assert `msg["direct_send_template_name"] == "weni_order_invoiced"` (or whatever the fixture's `Version.template_name` literal is — the post-FR-017-validation value with no substitution, no transformation). FR-014c(g).
  - **(c) Top-level sibling key**: assert `direct_send_template_name` is at the same nesting level as `msg.direct_send`, `msg.category`, and `msg.text` — a direct key on `msg`, NOT nested under any sub-object. The assertion is structural (`isinstance(msg.get("direct_send_template_name"), str)`); reading `msg["direct_send_template_name"]["..."]` MUST raise `TypeError`. FR-014c(g).
  - **(d) Locale is dropped from the wire**: same fixture, parameterized with a non-default locale (e.g. `metadata.language="es_MX"`); assert `"locale" not in msg` AND `"language" not in msg` AND `msg.get("template")` is None (no nested locale either). FR-014c(f) — no language hint on the wire. **Internal-locale invariant**: `Broadcast._resolve_language` (`broadcast.py:737`) MUST still be invoked for `BroadcastMessage` persistence and legacy `_send_to_datalake` payload purposes; assert the persisted `BroadcastMessage` row (or the datalake send call captured via mock) carries the resolved locale even though the wire `msg` does not. This pins FR-014c(f)'s "compute internally, omit from wire" rule against a future refactor that drops `_resolve_language` entirely.
  - **(e) Naming-rule refusal still gates the wire identifier**: invalid name (containing uppercase, hyphens, non-ASCII, or > 512 chars) → `build_direct_send_message` returns `None` AND emits the FR-039 `[BroadcastDispatch] skipped_due_to_direct_send_validation: project_uuid={...} agent={...} template={...} reason=naming_rule event={data}` audit-log line. The naming-validation gate at `broadcast.py:751` MUST be PRESERVED — refusing dispatch BEFORE any wire emission so the wire never carries an invalid `direct_send_template_name`. FR-014c(b) + FR-017. **Note**: T011b already pins the audit-log shape; this clause pins the gate's continued role as the wire-emission guard after the FR-014c(g) relocation.
  - **(f) Audit-log key unaffected (FR-014c(d))**: trigger any FR-039 refusal class (naming_rule, empty_body, component_length_limit) and assert the captured audit-log line still contains the literal substring `template=<template_name>` — i.e. the audit log's `template={...}` field is INTERNAL observability and is NOT renamed to `direct_send_template_name={...}` by FR-014c. The audit log keeps its existing identifier; ONLY the wire `msg` is affected by the FR-014c relocation.
  - **(g) Legacy path unaffected**: with `IntegratedAgent` whose `config.get("direct_send", False)` is `False`, `Broadcast.build_message` routes to `build_broadcast_template_message` which continues to emit `msg.template = {name, locale, variables}` byte-for-byte per FR-020 AND `msg.direct_send_template_name` is ABSENT from the legacy payload. Existing T033 snapshot test pins the legacy `msg.template` shape; add a one-line assertion to T033 (or a sibling regression method in `test_broadcast_legacy_payload.py`) confirming `"direct_send_template_name" not in legacy_msg`. The FR-014c relocation MUST NOT leak onto the legacy cohort.
  - **(h) `send_message` logging line behaviour**: the logging line at `Broadcast.send_message` (`broadcast.py:391`) currently reads `message.get("msg", {}).get("template", {}).get("name", ...)`. With T116's implementation, the Direct Send path's `msg` has no `template` key, so the current expression returns the fallback. Assert (i) the Direct Send-path dispatch log line still emits the resolved template name (whether via a new path-aware accessor `msg.get("direct_send_template_name") or msg.get("template", {}).get("name", ...)` OR via dedicated path branching), AND (ii) the legacy-path log line is byte-identical to today (no regression on the existing log shape per FR-027). Use `assertLogs` at INFO level to capture both cohorts.

  **Implementation contract**: in `Broadcast.build_direct_send_message` (`broadcast.py:804-811`), DELETE the `"template": {"name": template_name}` initializer and the conditional `msg["template"]["locale"] = language` assignment. Add `msg["direct_send_template_name"] = template_name` at the same top-level position (alongside `msg["direct_send"] = True`, `msg["category"] = "utility"`, and the FR-014d `msg["text"] = substituted_body` from T117). The `send_message` logging line at `broadcast.py:391` MUST be updated to read the template name path-aware — recommended form: `template_name = message.get("msg", {}).get("direct_send_template_name") or message.get("msg", {}).get("template", {}).get("name", "")` — so the legacy path continues to log via `msg.template.name` and the Direct Send path logs via the new key. NO new exception type is introduced; FR-017's naming-rule gate (the existing `is_valid_direct_send_template_name` check) is left in place verbatim — only the wire-emission location of the validated name changes. Mirror the FR-014c(d) audit-log preservation rule by NOT renaming the audit-log `template={...}` field anywhere; the audit log keeps its existing internal identifier.

- [X] T117 [US1] **FR-014d — rename wire key `msg.body` → `msg.text` (Session 2026-05-22 Q16 / Q18)** — Tests in `retail/agents/tests/services/test_broadcast_direct_send.py` AND dispatch implementation in `retail/agents/domains/agent_webhook/services/broadcast.py`. **Tests** (one method per branch):
  - **(a) Wire key is exactly `text`**: a Direct Send-enabled IntegratedAgent + a Template with body `"Olá {{1}}"` + `template_variables={"1": "Maria"}`; call `Broadcast.build_direct_send_message(...)`; assert `msg["text"] == "Olá Maria"` AND `"body" not in msg`. FR-014d(a) + FR-014d(b) — the key spelling is exact (`text`, lowercase, no synonyms).
  - **(b) Top-level sibling key**: assert `msg["text"]` is at the same nesting level as `msg["direct_send"]`, `msg["category"]`, and `msg["direct_send_template_name"]` (the FR-014c(g) sibling from T116); the value is a string. FR-014d(b).
  - **(c) Empty-body refusal preserves `reason=empty_body` (FR-014d(c))**: a Template whose `metadata.body` is missing or empty → `build_direct_send_message` returns `None` AND the FR-039 audit-log line includes the literal substring `reason=empty_body` (NOT `reason=empty_text`). The audit-log discriminator is internal observability and is preserved for log-consumer stability; ONLY the wire-key spelling is renamed. This pins FR-014d(c)'s "wire-vs-storage terminology drift is intentional" rule.
  - **(d) Length-limit refusal preserves `MAX_BODY_LENGTH` (FR-014d(c) + FR-014d(e))**: post-substitution `substituted_body` length > 1024 chars → `build_direct_send_message` returns `None` AND the audit-log line includes the literal substring `reason=component_length_limit`. Additionally, import `MAX_BODY_LENGTH` from `retail/agents/domains/agent_webhook/services/direct_send_constants.py` and assert the constant equals `1024` (snapshot the internal constant name + value against a future PR that would silently rename it to `MAX_TEXT_LENGTH`).
  - **(e) `_exceeds_direct_send_length_limits` continues to fire on body overflow**: same overflow fixture as (d); assert via `assertLogs` that the refusal happens at the gate (the function `_exceeds_direct_send_length_limits` at `broadcast.py:820-850` continues to read from `substituted_body` — the local variable — NOT from `msg["body"]` or `msg["text"]`); the wire-emission key rename does NOT change where the length check reads from. FR-014d(e).
  - **(f) `Template.metadata["body"]` storage unchanged (FR-014d(c))**: in `test_assign_direct_send.py` (or the sibling `test_broadcast_direct_send.py` if a persisted Template fixture is available), assert that an `AssignAgentUseCase.execute(...)` against a Direct Send-enabled channel persists `Template.metadata` with the key `"body"` (NOT `"text"`) — Meta's `body` field is written to `Template.metadata["body"]` verbatim, no rename. This pins the internal-storage preservation rule against a future PR that would propagate the wire rename into storage.
  - **(g) Legacy path unaffected**: with `IntegratedAgent.direct_send=False`, the legacy `build_broadcast_template_message` does NOT emit a `msg.text` key (the legacy path's body content is implicit in Meta's server-side template substitution; the legacy `msg` carries `msg.template = {name, locale, variables}` byte-for-byte per FR-020). Add a one-line assertion to T033 (or a sibling regression method in `test_broadcast_legacy_payload.py`) confirming `"text" not in legacy_msg`. The FR-014d rename MUST NOT leak onto the legacy cohort.

  **Implementation contract**: in `Broadcast.build_direct_send_message` (`broadcast.py:804-808`), rename ONLY the wire emission key from `msg["body"] = substituted_body` to `msg["text"] = substituted_body`. The local variable `substituted_body` keeps its name; the constant `MAX_BODY_LENGTH` in `direct_send_constants.py` keeps its name and value (1024); the FR-039 audit-log refusal-reason discriminator `reason=empty_body` keeps its spelling. `_exceeds_direct_send_length_limits` at `broadcast.py:820-850` reads body as a positional / keyword argument from the local `substituted_body` variable — that read site does NOT need to change because it never read from `msg["body"]` in the first place; only the wire-emission key is renamed. No other code path is affected. The `Template.metadata["body"]` persistence in `AssignAgentUseCase._create_library_templates` (and in the `_meta_library_template_fetch.py` adapter) is UNCHANGED — wire-only rename per FR-014d(c).

- [X] T118 [docs] **Contract artifact correction (FR-014c(c) / FR-014d(g))** — Edit `contracts/messaging-gateway-payload.md` to reflect the FR-014c + FR-014d wire shapes. Mirrors T115's precedent (the contract follows the spec, not vice versa — same as FR-003e for the `header` shape). Required edits:

  (a) **§3.1 — Direct Send `msg` example**: remove the `"template": {"name": "...", "locale": "..."}` block; add `"direct_send_template_name": "<Version.template_name>"` as a top-level sibling key alongside `"direct_send": true`, `"category": "utility"`, and `"text": "<substituted body>"`. Replace every `"body": "<substituted body>"` occurrence with `"text": "<substituted body>"`. The §3.1 field table MUST be updated accordingly: the `template` row is REMOVED; new rows for `direct_send_template_name` and `text` are added; the `body` row is renamed to `text` (the prose description MAY retain the word "body" since FR-014d(c) preserves "body" as the content concept — only the JSON-key spelling is renamed).
  (b) **§3.3 — sub-section heading + sub-field tables**: remove every `template.name` / `template.locale` reference from §3.3 (the Direct Send path no longer carries `msg.template`); the existing §3.3 (post-T115) covers CTA URL + Quick Replies on the Direct Send path — extend the §3.3 header note to confirm the absence of `msg.template` (cite FR-014c(a)).
  (c) **§3.4 — "Behavioural guarantees" substitution-target bullet**: the bullet that enumerates substitution targets MUST be rewritten to read `text`, `header.text`, `footer`, `cta_message.display_text`, `cta_message.url`, `quick_replies[*]` (drop `body` — wire-key is now `text` per FR-014d; drop `template.name` / `template.locale` — they are no longer on the wire per FR-014c).
  (d) **§5.1 / §5.1b / §5.1c / §5.2 — examples**: in every Direct Send example, (i) replace `"template": {"name": ..., "locale": ...}` with the top-level sibling `"direct_send_template_name": "..."` on `msg`; (ii) rename every `"body": "..."` JSON-key occurrence to `"text": "..."`. Each example MUST be the canonical post-FR-014c / post-FR-014d shape end-to-end.
  (e) **§3.5 or new §3.6 — "Spec is canonical" note**: extend the existing §3.5 (introduced by T115) — OR add a sibling §3.6 with the same heading — to also cover FR-014c / FR-014d. The statement: "FR-014c (drop `msg.template`, add `msg.direct_send_template_name`, drop wire locale) and FR-014d (rename wire key `msg.body` → `msg.text`) restate the canonical wire shape; any future drift between this contract and `spec.md` resolves in favour of the spec — same precedent as FR-003e / FR-014a / FR-014b."
  (f) **§2.x — legacy path UNTOUCHED**: legacy templates continue to carry `msg.template = {name, locale, variables}` byte-for-byte per FR-020. The contract preserves §2.1 / §2.2 / §2.3 / §2.4 verbatim against this requirement; the T118 grep gate below intentionally allows matches inside §2.x.

  **Verification (single-pass grep gate — canonical for FR-014c / FR-014d)**: after the edits, run:

  ```bash
  rg -n '"template":\s*\{|"body":\s*"|msg\.template|msg\.body|"locale":\s*"' \
    specs/002-direct-send-broadcasts/contracts/messaging-gateway-payload.md
  ```

  Every match MUST land inside §2.x (legacy path, bit-for-bit preserved per FR-020) OR inside an explicit "SUPERSEDED" / "Historical note" / "**⚠️**" block. Zero matches are permitted inside §3.x or §5.x. The legacy §2.1 example is the canonical home for `msg.template = {name, locale, variables}` and is intentionally retained by this gate. Re-run the T115 grep gate in parallel (`rg -n 'sub_type":\s*"cta_url"|sub_type":\s*"reply"' contracts/messaging-gateway-payload.md`) to confirm the FR-014a / FR-014b survivors remain zero; the full merge gate is the union of both grep commands plus the T106 verification recipe (which catches operator-facing-artefact drift in `quickstart.md`, `research.md`, `data-model.md`).

- [ ] T119 *(intentionally reserved — slot kept open for a future incremental fold-in between T118 and T120 without renumbering existing tasks)*

### Implementation for Phase 8 (original — T120; FR-003e / FR-003f / Q3 drop-rule)

> **Code change scope** (informational — NOT in the spec-only fold-in
> PR): the adapter `adapt_meta_library_template_response` at
> `retail/templates/usecases/_meta_library_template_fetch.py` is the
> single touch point for all three rules. Read T107–T111's assertions
> as the contract the implementation MUST satisfy; the
> implementation is delivered in a separate code-change PR.

- [X] T120 [US2] Tighten `adapt_meta_library_template_response` in `retail/templates/usecases/_meta_library_template_fetch.py` to satisfy T107–T111. Reuse the existing `DirectSendUnsupportedComponentError` (T007); set `component_type` to one of `"header"`, `"<button.type>"`, `"<component>"`, or `"malformed"` so audit logs and DRF error responses carry a stable discriminator. The four rejection branches (header shape, button type, length/count overflow, malformed JSON) collapse to the same exception class so the use case keeps a single FR-003c → FR-003d routing path. URL-button shape normalization MUST go through the same `_ensure_protocol` + `_append_placeholder_if_needed` heuristic the push-path `ButtonTransformer` already applies — extract a shared helper if needed rather than duplicating. The auxiliary-field drop MUST be applied at the top of the adapter (before validation) so length-limit and component-type checks see only the dispatch-relevant subset.

**Checkpoint**: Phase 8 complete when:

1. **Original scope (T107–T111, T120)** — pins FR-003e / FR-003f /
   the Q3 auxiliary-field drop. Closes `/speckit-analyze` 2026-05-21
   findings on adapter coverage.
2. **First extension scope (T112–T115)** — pins FR-003g (override
   map), FR-014a (CTA URL wire shape), FR-014b (quick_replies wire
   shape), and corrects the contract artifact for those rules.
   Closes `/speckit-analyze` 2026-05-22 (first pass) findings
   C1 / C2 / C3 (CTA URL wire shape, QUICK_REPLY wire shape,
   override map coverage gaps), H1 / H2 / H3 / H4 / H5 (plan
   fold-in, Phase 8 scope, T011a / T013 contradictions,
   contract-correction surface), M1 / M3 (combined-case regression
   guard, length-limit refusal location), L1 / L2 (cross-references).
3. **Second extension scope (T116–T118)** — pins FR-014c (drop
   `msg.template`, add `msg.direct_send_template_name`, drop wire
   locale), FR-014d (rename wire key `msg.body` → `msg.text`,
   wire-only — internal storage preserved), and corrects the
   contract artifact for those rules. Closes `/speckit-analyze`
   2026-05-22 (second pass) findings C1 / C2 / C3 (FR-014c /
   FR-014d coverage gaps + stale OUTSTANDING WORK banner),
   H1 / H2 / H3 / H4 / H5 / H6 (T011 / T014 overlay drift,
   T115 / T106 grep-gate blindspot, missing happy-path assertion
   for `msg.direct_send_template_name`, missing deploy-coordination
   plan sub-section), M1 / M2 / M3 / M4 / M5 / M6 (plan summary /
   constraints fold-in, Phase 8 second-extension labels,
   independent-test wording, audit-log-not-affected overlay,
   Constitution Check re-evaluation), L1 / L2 (Phase 4 Independent
   Test FR-014d(c) cross-reference, recommended-PR-order block).

After all three scopes land, rerun `/speckit-analyze` and confirm
the C / H findings clear. Rerun `poetry run python
contrib/compare_coverage.py` and confirm `Number of test lines
decreased` is NOT reported (T011a's `[~] SUPERSEDED` removal of the
old QUICK_REPLY assertions is offset by T114's new-shape assertions
plus T112 / T113's new branches; T116 / T117 introduce net-new
test methods on the FR-014c / FR-014d surface, so the second-
extension net delta is strictly positive).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **BLOCKS** all user stories.
- **US1 (Phase 3)**: Depends only on Foundational. Sequential entry point for the rest of the work.
- **Spec correction (Phase 3.5)**: Depends on US1 (Phase 3) being complete (Phase 3.5 retroactively corrects the `direct_send` storage scheme introduced by US1's T002). **MUST run BEFORE Phase 4 (US2)** so US2 fixtures and implementation are authored against the canonical `IntegratedAgent.config["direct_send"]` JSON-key form from the start, AND **MUST run BEFORE Phase 7 (T036–T039)** so the polish/coverage/PR phase runs against the canonical shape from `data-model.md §1`, not the superseded column form. Strictly speaking the phase touches only the agents-side storage (US2/US3/US4 are independent of it for code correctness because their tasks already specify the JSON-key form per T104's "task description sweep"), but running it BEFORE US2 caps the surface T104 has to migrate at the existing US1 fixture set rather than letting US2/US3/US4 fixtures grow it.
- **User Stories (Phases 4–6)**: All depend on Foundational AND on Phase 3.5 being complete. After Phase 3.5, US2/US3/US4 run independently — sequentially (P2 → P3 → P4) for a single implementer or in parallel for a multi-developer team.
- **Polish (Phase 7)**: Depends on every desired user story being complete (Phases 3, 4, 5, 6) AND on Phase 3.5 being complete. Running T037 (coverage parity) or T039 (open PR) before Phase 3.5 would ship the wrong storage scheme.
- **Post-implementation fold-in (Phase 8)**: Added after Phase 7 closed out, to cover the Session 2026-05-22 spec clarifications. Phase 8 ships in THREE scopes:
  - **Original scope (T107–T111, T120)** — covers FR-003e, FR-003f, and the Q3 auxiliary-field drop-rule. T107–T111 are authored red against the current adapter, then T120 makes them green. Depends on Phase 4 (US2 — the adapter is the touch point) and Phase 7 (the baseline implementation must already be in main).
  - **First extension scope (T112, T113, T114, T115)** — covers FR-003g (override map), FR-014a (CTA URL wire shape), FR-014b (QUICK_REPLY wire shape), and the first contract artifact correction. Depends on the original Phase 8 scope (T120's adapter rules are the foundation T112 extends), Phase 4 (US2 — adapter touch point for T112), Phase 3 (US1 — dispatch builder touch point for T113 + T114), and Phase 7 (baseline implementation). Within the first extension, run order is **T112 → T113 → T114 → T115** (adapter override map → CTA URL dispatch → QUICK_REPLY dispatch → contract artifact correction). T112 / T113 / T114 / T115 are all `[X]` and have already landed.
  - **Second extension scope (T116, T117, T118, T119 reserved)** — covers FR-014c (drop `msg.template`, add `msg.direct_send_template_name`, drop wire locale), FR-014d (rename wire key `msg.body` → `msg.text`, wire-only — internal storage preserved per FR-014d(c)), and the second contract artifact correction. Depends on Phase 3 (US1 — dispatch builder is the touch point for T116 + T117), Phase 7 (baseline implementation), and Phase 8 first extension (T112–T115 — T116 / T117 stack on top of the FR-014a / FR-014b wire-shape relocation; modifying the same `Broadcast.build_direct_send_message` method). Within the second extension, run order is **T116 → T117 → T118** (FR-014c dispatch builder → FR-014d dispatch builder → contract artifact correction); T116 and T117 touch overlapping lines in `broadcast.py:804-822`, so the in-order authoring keeps each commit's diff scoped to a single FR. T116 / T117 / T118 are `[ ]` and are the OUTSTANDING WORK BEFORE MERGE callouts pinned at the top of this file. T119 is intentionally reserved (unused) so a future incremental fold-in can fit between T118 and T120 without renumbering existing tasks.

  Phase 8 in any scope is a strict superset of US2's adapter contract / US1's dispatch contract; running any scope before Phase 4 / Phase 3 has no meaning. **Rerun the Phase 7 coverage-parity gate (T037 / `compare_coverage.py`) AND the Phase 7 quickstart gate (T036) AT THE END OF EACH PHASE-8 SCOPE** so T107–T111 + T120 + T112 + T113 + T114 + T116 + T117 count toward the merge floor (see the Phase 7 re-run gate inline note above T036 — note that the gate's bullet list MUST itself be re-extended at the end of the second extension to cite T116 / T117 / T118 alongside the existing T112 / T113 / T114 / T115 entries). Without the re-run, T011a's `[~] SUPERSEDED by T114` removal of the original QUICK_REPLY assertions is not offset by T114's replacements in the coverage floor and the merge gate is structurally satisfied only on paper; without the second-extension re-run, T116 / T117's wire-shape corrections never reach the coverage / quickstart merge floor.

### User Story Dependencies

- **US1 (P1)**: Depends only on Foundational (T002, T004, T007). Tested via fixtures; does not need US2's assignment flow. T014a (dedup regression), T014b (FR-031 official-agent precedence regression), T014c (FR-030 different-`current_state` regression), and T014d (unpause-race regression — depends additionally on T031's unified dispatch-gate skip shape from US3) additionally depend on T014 — the dispatch branching done by T014 is what allows the dedup and resolution mechanisms to admit a Direct Send-enabled IntegratedAgent end-to-end. T116 (FR-014c) and T117 (FR-014d) additionally depend on the Phase 8 first extension (T113 + T114) being complete — they modify the same `Broadcast.build_direct_send_message` method that T113 / T114 already touch — and on T011 / T013 / T014 having shipped to provide the dispatch-builder surface they correct. T014d is `[X]`; T116 / T117 / T118 are `[ ]` and are the OUTSTANDING WORK BEFORE MERGE callouts pinned at the top of this file.
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
- All `[P]` tests within a single phase touch different files and run in parallel. **Exception**: the T011/T011a–T011d cluster shares `test_broadcast_direct_send.py` (T011e lives in the sibling `test_broadcast_direct_send_persistence.py` so the persistence-focused fixtures stay separated from the wire-shape fixtures), the T018/T018a–T018e cluster shares `test_assign_direct_send.py`, and the T014a/T014c/T014d cluster shares `test_order_status_dedup_direct_send.py`. The sub-tasks within each cluster are still independent test methods on disjoint scenarios (naming-rule vs. empty-body vs. happy-path; same-tuple-dedup vs. different-`current_state`-dispatch vs. unpause-race-during-dedup-window; new-assignment vs. re-assignment-after-`is_active=False`, etc.), so they can be authored in any order by separate developers and merged sequentially without conflict; the `[P]` tag denotes task-level parallelism for multi-developer assignment, not file-level isolation.
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
