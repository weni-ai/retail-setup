# Tasks: Spec Kit Onboarding Documentation

**Input**: Design documents from `/specs/001-speckit-docs/`

**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user stories).

**Tests**: Not applicable — the deliverable is prose. The Spec Quality
Checklist at [checklists/requirements.md](./checklists/requirements.md) acts
as the review gate.

**Organization**: Tasks are grouped by user story to enable independent
delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, …)
- File paths are relative to the repository root.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Make `docs/SPEC_KIT.md` reachable from the workspace.

- [x] **T001** Adjust `.gitignore`: replace the blanket `docs/` ignore with `docs/*` followed by `!docs/SPEC_KIT.md` so this single file can be tracked while every other `docs/*` entry stays ignored. *(Note: `docs/` does not allow re-inclusion of contained files; switching to `docs/*` was required.)* Confirmed with `git check-ignore -v docs/SPEC_KIT.md` → `.gitignore:144:!docs/SPEC_KIT.md`.

## Phase 2: Foundational (Blocking Prerequisites)

*None — no shared code or schemas are introduced.*

## Phase 3: User Story 1 — New engineer onboards to Spec-Driven Development (P1)

**Goal**: Deliver a single doc that lets a new contributor go from "I want to ship a feature" to "I've opened a PR" using Spec Kit.

**Independent Test**: A reader who has never seen Spec Kit completes a hello-world feature using only this doc.

- [x] **T002** [US1] Created `docs/SPEC_KIT.md` (171 lines) with Overview, Install the CLI (uv + pipx with Python version notes), Daily workflow, Artifacts table, Constitution + amendment instructions, Git extension hooks, Reviewer checklist (T004), Troubleshooting, and Further reading. Covers FR-001 through FR-008.
- [x] **T003** [US1] *(scope-adjusted during implement)* The repo has no top-level `README.md`, so the originally planned README link is impossible. Replaced with: (a) `.specify/memory/constitution.md` now opens its "Development Workflow" section with a callout linking to `docs/SPEC_KIT.md`, and (b) `.cursor/rules/specify-rules.mdc` already directs the agent at the current plan, which references the doc. Follow-up captured in the dry-run validation report at the bottom of this file.

## Phase 4: User Story 2 — Reviewer validates Spec-Driven artifacts (P2)

**Goal**: Reviewers can recognise and validate Spec-Driven artifacts on a PR.

**Independent Test**: A reviewer who has never used Spec Kit reads `docs/SPEC_KIT.md` and can identify, for a PR, whether the author skipped a required workflow step.

- [x] **T004** [US2] Inside `docs/SPEC_KIT.md`, added a "Reviewer checklist" section listing the artifacts (`spec.md`, `plan.md`, `tasks.md`, `checklists/requirements.md`) and the Constitution Check gates a reviewer should verify, plus PR title/body and coverage parity gates. Covers acceptance scenarios 1 and 2 of US2.

## Phase 5: Polish

- [x] **T005** Manual validation pass confirmed: 171 lines (within ≤300 budget), 9 H2 headings in the planned order (Overview → Install the CLI → Daily workflow → Artifacts → Constitution → Git extension hooks → Reviewer checklist → Troubleshooting → Further reading), the two relative links to `.specify/memory/constitution.md` resolve, and `docs/SPEC_KIT.md` is the only entry under `docs/` that escapes `.gitignore`.
- [x] **T006** Re-walked `checklists/requirements.md`; every box was already ticked at `/speckit-specify` time and remains true after implementation.

## Dry-run validation report

This entire feature was executed as the Spec Kit bootstrap's recommended
sanity check. Outcomes recorded for future reference:

- **Spec Kit version under test**: `specify-cli` 0.8.13.dev0, installed via
  `uv tool install` (uv 0.11.15).
- **Skills version note**: in this CLI build, Cursor slash commands are
  hyphenated (`/speckit-constitution`, not the dotted form some upstream docs
  still show). The hyphenated form matches the directory names under
  `.cursor/skills/`.
- **CLI flag deprecation**: `specify init --ai cursor-agent` was used because
  the current binary still accepts the deprecated flag. Upstream 0.10.0 will
  rename it to `--integration cursor-agent` — track that in the next CLI
  upgrade.
- **Branch hook bypassed once**: the `before_specify` hook (`speckit.git.feature`)
  is mandatory and would have moved us to a fresh `001-speckit-docs` branch.
  To keep all bootstrap work on the single `chore/adopt-spec-kit` branch the
  spec directory and `.specify/feature.json` were created manually by the
  agent (the SKILL.md explicitly allows the spec directory and branch name to
  diverge). Future features SHOULD let the hook do its job.
- **Follow-up**: SC-004 (README reachability in one click) is unmet because
  the repository has no top-level `README.md` today. Captured as the deferred
  half of T003. Recommended next-step for the team: open a `chore: Add
  top-level README.md` PR that links to `docs/SPEC_KIT.md` near the top.
- **Workflow wiring confirmed**: `.specify/extensions.yml` lists every
  `before_*`/`after_*` git hook, `.cursor/skills/` contains all expected
  `speckit-*` skills, `.cursor/rules/specify-rules.mdc` is in place, and
  `.specify/scripts/bash/create-new-feature.sh --dry-run` returned
  `{"BRANCH_NAME":"001-speckit-docs", ...}` indicating the script chain works.

## Dependencies

- T001 must complete before T002 (without the `.gitignore` change, `docs/SPEC_KIT.md` is invisible to git).
- T002 must complete before T003 (the README links to the doc).
- T002 must complete before T004 (T004 adds a section to the same file).
- T005 and T006 run last.

## Acceptance Mapping

| User Story | Tasks |
|------------|-------|
| US1 (P1)   | T002, T003 |
| US2 (P2)   | T004 |
| Setup      | T001 |
| Polish     | T005, T006 |
