<!--
SYNC IMPACT REPORT
==================
Version change: (none) → 1.0.0
Ratified: 2026-05-20
Bump rationale: Initial ratification. No prior version existed; this constitution
codifies the engineering standards already enforced by the project's Cursor rules
(`~/.cursor/rules/code-agent.mdc`, `~/.cursor/rules/test-coverage-and-external-dependencies.mdc`,
`~/.cursor/rules/comments-and-self-documenting-code.mdc`) into a Spec-Driven
Development governance document.

Principles introduced:
  I.   Layered Clean Architecture (NON-NEGOTIABLE)
  II.  DRF Composition for AuthN/AuthZ
  III. Test Coverage Parity & Isolated Tests (NON-NEGOTIABLE)
  IV.  Self-Documenting Code
  V.   Conventional Commits & Structured PRs

Sections added:
  - Additional Engineering Standards
  - Development Workflow
  - Governance

Templates reviewed for alignment:
  ✅ .specify/templates/plan-template.md — Constitution Check section references
     this file; gates will be derived per-feature.
  ✅ .specify/templates/spec-template.md — no changes required (spec stays
     technology-agnostic; principles apply at plan/tasks/implement time).
  ✅ .specify/templates/tasks-template.md — no changes required at v1.0.0;
     existing task categorization already accommodates testing + coverage gates.
  ✅ .cursor/rules/specify-rules.mdc — no changes; rule points the agent at
     the current plan, which in turn references this constitution.

Follow-up TODOs: none.
-->

# retail-setup Constitution

## Core Principles

### I. Layered Clean Architecture (NON-NEGOTIABLE)

All new code MUST respect the layered boundary `Views → Use Cases → Services → Clients`, with `Interfaces` (typing.Protocol) expressing client contracts.

- **Views** are thin: they validate input via a `Serializer`, build a frozen `DTO`, delegate to a Use Case, and shape the HTTP `Response`. Views MUST NOT call `Model.objects.*`, MUST NOT contain business logic, and MUST NOT import infrastructure clients directly.
- **Use Cases** are framework-agnostic: they hold business rules, orchestrate services, run ORM queries, and raise domain or DRF exceptions. Use Cases MUST NOT import anything from `rest_framework` (no `Request`, `Response`, `status`, or permissions) and MUST NOT touch `request` objects.
- **Services** wrap clients, catch infrastructure exceptions, log context, and return `None` on failure. Services MUST NOT propagate raw infrastructure errors upward.
- **Clients** are the only layer allowed to perform outbound HTTP calls; each client implements a `Protocol` interface and is injected via `__init__` (with an `Optional` fallback to the concrete implementation).

**Rationale**: Mixing layers is the most common defect class in the current codebase. Locking the boundary at the constitution level gives every plan a hard test.

### II. DRF Composition for AuthN/AuthZ

Authentication and authorization are expressed exclusively through DRF `permission_classes` on the view class, composed with `&`/`|` operators when conditions are mixed.

- Permission logic MUST NOT appear inside view method bodies (no manual `self.check_object_permissions(...)`, no `if request.user...`).
- Permission logic MUST NOT appear inside Use Cases or Services.
- Custom permissions MUST inherit from `BasePermission` so they remain composable.

**Rationale**: Centralising access control on the view boundary keeps Use Cases reusable across CLI, Celery, and consumer entrypoints, and prevents the silent privilege drift that occurs when checks are scattered.

### III. Test Coverage Parity & Isolated Tests (NON-NEGOTIABLE)

Every PR MUST sustain or raise the project coverage measured by `coverage run manage.py test` and `contrib/compare_coverage.py`.

- Every new or modified function/branch MUST be exercised by a unit or integration test in the same PR.
- Code that genuinely cannot be tested in-repo (live external providers, broker-only consumers, defensive `__main__` blocks) MUST be marked with `# pragma: no cover` and an inline justification. `# pragma: no cover` MUST NOT be used to bypass writing tests for business logic.
- Tests MUST NOT reach real infrastructure: cache, queue, OIDC, S3, Connect, Lambda, and other external dependencies MUST be overridden (e.g. `@override_settings(CACHES={"default": LocMemCache})`) or mocked at the client boundary.
- Integration tests SHOULD be preferred over heavy mocking when an in-process alternative exists (SQLite in-memory, LocMemCache, etc.).

**Rationale**: CI must never silently degrade because Redis/RabbitMQ/Postgres are unavailable, and feature work must not erode the coverage floor that protects the rest of the codebase.

### IV. Self-Documenting Code

Names carry intent; comments explain *why*, never *what*.

- Function and variable names MUST express purpose; if a block of code needs a narrative comment to be understood, extract it into a private method whose name conveys the intent (Replace Comment with Function).
- Comments are reserved for non-obvious intent, trade-offs, ordering constraints, or references to external contracts. Redundant, narrative, or commented-out code MUST be removed.
- Logging uses f-strings, includes the relevant identifier(s) (e.g. `order_id`, `project_uuid`), and respects the level semantics (`info` for milestones, `warning` for recoverable anomalies, `error` for failures with context).
- Single Level of Abstraction (SLAP): a single method MUST NOT mix business flow with formatting, serialization, or logging boilerplate.

**Rationale**: Comments rot; well-named code does not. Extracting narrative blocks into methods turns documentation into structure that the compiler/test runner can verify.

### V. Conventional Commits & Structured PRs

All commits MUST follow [Semantic Commit Messages](https://gist.github.com/joshbuchea/6f47e86d2510bce28f8e7f42ae84c716): `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`, `style:`.

- Branch names follow `<type>/<kebab-case-description>` using the full word form (e.g. `feature/`, `fix/`, `refactor/`, `chore/`).
- PR titles are limited to **72 characters** and start with the same type prefix.
- PR descriptions MUST contain both a `## What` section (short description of intent) and a `## Why` section (justification).
- New Django models MUST follow the integer primary key + `uuid` (`unique=True`, not PK) pattern; legacy models keep their existing PK strategy.

**Rationale**: A predictable commit/PR shape lets reviewers, automation, and changelog tooling rely on the metadata instead of re-deriving intent from code diffs.

## Additional Engineering Standards

- **Stack**: Python 3.10, Django 5, Django REST Framework 3.15, Celery + Redis, Postgres via `psycopg2`, `weni-eda` for event-driven flows, `mozilla-django-oidc` for auth, Babel for i18n, `boto3` for AWS clients, Sentry + Elastic APM for observability.
- **Dependency injection**: Always through `__init__` with `Optional[Interface] = None` and a fallback to the concrete implementation.
- **Naming**: English identifiers; `PascalCase` classes with explicit suffixes (`UseCase`, `Service`, `Client`, `DTO`, `Serializer`, `Interface`, `Error`); `snake_case` functions; Celery tasks prefixed `task_`.
- **Translations / i18n**: All locale files in `**/locales/**` follow the VTEX Content Guide (sentence case, no trailing period on labels, gender-neutral language, glossary terms). Keys MUST be snake_case nested under namespaces, and every key MUST exist in all language files with identical placeholder shape.
- **Settings & secrets**: All configuration via `django-environ` (`env.str()`, `env.bool()`, `env.int()`, `env.json()`). Secrets default to `""` and MUST NOT be committed.
- **Error handling**: Use Cases raise domain or DRF exceptions; Services swallow infrastructure errors and return `None`; Views translate domain exceptions into HTTP responses; fail-safe utilities (status marking, notifications) MUST NOT propagate their own exceptions.

## Development Workflow

> New to Spec-Driven Development? Read [docs/SPEC_KIT.md](../../docs/SPEC_KIT.md) for the contributor onboarding (CLI install, command order, artifact map, reviewer checklist, troubleshooting).

Every non-trivial change MUST flow through Spec-Driven Development:

1. `/speckit-constitution` — establish or amend principles (this document).
2. `/speckit-specify` — capture the *what* and *why* for the feature; technology-agnostic.
3. `/speckit-clarify` — resolve ambiguous areas before planning.
4. `/speckit-plan` — produce a `plan.md` that names the stack and architecture, runs the Constitution Check gate, and lists `[NEEDS CLARIFICATION]` items.
5. `/speckit-tasks` — generate an actionable task list whose categories include explicit testing and coverage tasks.
6. `/speckit-analyze` *(recommended)* — cross-artifact consistency review before implementing.
7. `/speckit-implement` — execute tasks while honouring the principles above.

Quality gates that MUST pass before merging:

- `poetry run coverage run manage.py test && poetry run coverage report -m` shows no regressions on changed files.
- `poetry run python contrib/compare_coverage.py` does not report `Number of test lines decreased`.
- `pre-commit` hooks (Black, flake8, configured via `.pre-commit-config.yaml`) run clean.
- The PR description follows the `What` / `Why` template above and the title respects the 72-character ceiling.

## Governance

This constitution supersedes ad-hoc engineering practices. All PRs and reviews MUST verify compliance with the principles above; deviations MUST be justified in the plan's `Complexity Tracking` table.

Amendment procedure:

1. Open an `/speckit-constitution` session describing the proposed change.
2. The version is bumped by the `speckit-constitution` skill following semantic versioning:
   - **MAJOR** — backward-incompatible removal or redefinition of a principle.
   - **MINOR** — new principle or materially expanded guidance.
   - **PATCH** — clarifications, wording, typo fixes.
3. The Sync Impact Report at the top of this file MUST be updated to record the change and to list templates that required follow-up.
4. The constitution PR MUST follow the `docs:` commit prefix.

Compliance review: every plan's Constitution Check section reads from this document. A failed gate blocks the plan from advancing to `/speckit-tasks` unless an explicit justification is recorded in `Complexity Tracking`.

**Version**: 1.0.0 | **Ratified**: 2026-05-20 | **Last Amended**: 2026-05-20
