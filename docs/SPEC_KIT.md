# Spec Kit (Spec-Driven Development) on retail-setup

This project uses **[GitHub Spec Kit](https://github.com/github/spec-kit)** to
drive non-trivial work through a `constitution → specify → clarify → plan →
tasks → analyze → implement` lifecycle. This document is the contributor
onboarding for that workflow.

## Overview

Spec-Driven Development means we write down *what* we are building and *why*
before we write production code. Every step produces a versioned artifact that
the next step consumes, so design choices, gates, and trade-offs are reviewable
and traceable.

| Phase | Command | Output |
|-------|---------|--------|
| Constitution | `/speckit-constitution` | `.specify/memory/constitution.md` |
| Specify | `/speckit-specify <description>` | `specs/NNN-<slug>/spec.md` and `checklists/requirements.md` |
| Clarify (recommended) | `/speckit-clarify` | Resolved `[NEEDS CLARIFICATION]` markers in `spec.md` |
| Plan | `/speckit-plan <tech context>` | `specs/NNN-<slug>/plan.md` (plus optional `research.md`, `data-model.md`, `contracts/`, `quickstart.md`) |
| Tasks | `/speckit-tasks` | `specs/NNN-<slug>/tasks.md` |
| Analyze (recommended) | `/speckit-analyze` | Cross-artifact consistency report |
| Implement | `/speckit-implement` | Production code matching the plan + tasks |

Optional companion: `/speckit-checklist` — generate quality checklists for a
specific concern (e.g., "tests-for-English") at any point after `/speckit-plan`.

## Install the CLI

Spec Kit ships as a Python CLI. It runs **independently** of the project's
Python 3.10 runtime; install it as a global tool.

### Recommended: `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # installs uv to ~/.local/bin
exec $SHELL -l                                     # reload PATH
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify --version                                  # confirm install
```

### Fallback: `pipx`

`pipx` works if you already have it, but it MUST run under Python 3.11+. On
this team's stock setup that means pointing it at a pyenv-managed interpreter:

```bash
pipx install --python ~/.pyenv/versions/3.12.8/bin/python \
  git+https://github.com/github/spec-kit.git
specify --version
```

### Upgrading

```bash
uv tool upgrade specify-cli          # uv
pipx upgrade specify-cli             # pipx
```

After upgrading the CLI, refresh the bundled templates inside the repo with
`specify integration upgrade cursor-agent` (run from the repo root).

## Daily workflow

1. **Pick a feature.** Decide what you want to build before opening Cursor.
2. **Open Cursor at the repo root.** The agent automatically picks up
   `.cursor/skills/` (slash commands) and `.cursor/rules/specify-rules.mdc`
   (which directs the agent at the current plan).
3. **Run the commands in order.** Each `/speckit-*` command writes its
   artifact and tells you what to run next. Stop whenever the agent surfaces a
   `[NEEDS CLARIFICATION]` marker and answer it before proceeding.
4. **Auto-commit hooks.** The `git` Spec Kit extension is installed by default
   in this project and creates a feature branch on `/speckit-specify`
   (mandatory) and offers to auto-commit on every `after_*` hook (optional).
   You can opt out of any optional commit when prompted.

## Artifacts under `specs/NNN-<slug>/`

| File | Owner | Purpose |
|------|-------|---------|
| `spec.md` | `/speckit-specify` | The *what* and *why* — user stories, requirements, success criteria, assumptions. Technology-agnostic. |
| `checklists/requirements.md` | `/speckit-specify` | Spec quality gate — completeness, testability, measurable success. |
| `plan.md` | `/speckit-plan` | The *how* — tech context, Constitution Check gates, project structure, phase outputs. |
| `research.md` | `/speckit-plan` | Phase 0 — resolves `[NEEDS CLARIFICATION]` items via decisions + rationale + alternatives. Omitted when there are no unknowns. |
| `data-model.md` | `/speckit-plan` | Phase 1 — entities, relationships, constraints. Omitted for features that touch no data. |
| `quickstart.md` | `/speckit-plan` | Phase 1 — minimal walkthrough for running/testing the feature. Omitted when the deliverable IS a doc. |
| `contracts/` | `/speckit-plan` | Phase 1 — external contracts (OpenAPI, message schemas). Omitted when the feature has no external surface. |
| `tasks.md` | `/speckit-tasks` | Phase 2 — actionable, ordered task list grouped by user story. |

Spec directories are committed; they ARE the design history.

## Constitution

The non-negotiable principles for this codebase live at
[.specify/memory/constitution.md](../.specify/memory/constitution.md) and are
re-evaluated as a gate inside every plan's **Constitution Check** section.

At v1.0.0 the principles are:

1. **Layered Clean Architecture** (Views → Use Cases → Services → Clients).
2. **DRF Composition for AuthN/AuthZ** (permissions live on the view class).
3. **Test Coverage Parity & Isolated Tests** (CI never talks to real infra).
4. **Self-Documenting Code** (names carry intent; comments explain *why*).
5. **Conventional Commits & Structured PRs** (`feat:`/`fix:`/`refactor:`/…,
   72-char titles, `## What` / `## Why` body).

### Amending the constitution

NEVER edit `.specify/memory/constitution.md` by hand. Run `/speckit-constitution`
and describe the change. The skill handles semantic versioning, updates the
Sync Impact Report at the top of the file, and rechecks the dependent templates.

## Git extension hooks

The `git` Spec Kit extension is installed (see `.specify/extensions.yml`). It
exposes the following automation:

- **`speckit.git.feature`** — runs before `/speckit-specify`. Creates and
  switches to a numbered feature branch (e.g. `001-<slug>`).
- **`speckit.git.commit`** — runs after every `/speckit-*` write step.
  Optional; you can decline at the prompt.
- **`speckit.git.initialize`** — runs before `/speckit-constitution` only
  when the project does not yet have a git repository.

Disable a hook by setting `enabled: false` on its entry in
`.specify/extensions.yml`, or skip ad-hoc by answering "no" at the prompt.

## Reviewer checklist

When a PR includes a `specs/NNN-<slug>/` directory, the reviewer should
confirm:

- [ ] `spec.md` exists with all mandatory sections (User Scenarios,
      Requirements, Success Criteria) populated and no leftover
      `[NEEDS CLARIFICATION]` markers.
- [ ] `checklists/requirements.md` has every box ticked.
- [ ] `plan.md` includes a **Constitution Check** table that maps each
      principle from `.specify/memory/constitution.md` to a PASS / violation
      with justification.
- [ ] `tasks.md` groups tasks by user story (US1, US2, …) and the
      implementation closes them in the documented order.
- [ ] The PR title respects the 72-character ceiling and uses a Conventional
      Commits prefix; the body has `## What` and `## Why` sections.
- [ ] Coverage parity: `poetry run python contrib/compare_coverage.py` does
      not report `Number of test lines decreased`.

If any of the above fails, the PR is not ready for code review.

## Troubleshooting

- **`specify` command not found** — your `PATH` doesn't include `~/.local/bin`.
  Re-source your shell rc or add `export PATH="$HOME/.local/bin:$PATH"`.
- **`Not a spec-kit project (no .specify/ directory)`** — you ran `specify`
  outside the repo root, or the `.specify/` directory was removed.
- **Cursor doesn't show `/speckit-*` commands** — reload Cursor; the skills
  live under `.cursor/skills/` and are loaded at startup. If the directory
  was just created, restart Cursor.
- **Hook tried to create a branch I don't want** — the `before_specify` hook
  is mandatory by default. Either let it create the branch and rename later,
  or set `enabled: false` for `speckit.git.feature` in
  `.specify/extensions.yml` before invoking the command.
- **Coverage check fails on a PR with no logic change** — confirm you didn't
  reformat or restructure unit tests inadvertently; revert and rerun
  `contrib/compare_coverage.py`.

## Further reading

- Upstream project: <https://github.com/github/spec-kit>
- Official integrations table: <https://github.github.io/spec-kit/reference/integrations.html>
- Constitution skill internals: `.cursor/skills/speckit-constitution/SKILL.md`
- Project constitution (current version): [.specify/memory/constitution.md](../.specify/memory/constitution.md)
