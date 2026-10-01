<!--
SYNC IMPACT REPORT
==================
Version change: 1.0.0 → 2.0.0
Ratified: 2026-05-20 (preserved)
Last Amended: 2026-10-01
Bump rationale: MAJOR. The project constitution is now synthesized from the
VTEX CX engineering base constitution (root) and the backend base
constitution. Two existing principles were redefined in a backward-incompatible
way: the allowed commit types no longer include `style:` and commit
descriptions are capped at 50 characters (root "Commit Messages" prevails);
"DRF Composition for AuthN/AuthZ" was absorbed into "Never Trust the Client".

Modified principles:
  I.   Layered Clean Architecture           → I.   Layered Clean Architecture (unchanged intent; error-handling rules aligned with III/IV)
  II.  DRF Composition for AuthN/AuthZ      → II.  Never Trust the Client (absorbs II; adds webhook/inter-service input validation)
  III. Test Coverage Parity & Isolated Tests → IX. Tests Exercise Flows & Coverage Parity (adds mandatory flow test + failure paths)
  IV.  Self-Documenting Code                → X.   Explicit Over Clever (adds named-constant rule for meaningful literals; structured logging moved to VII)
  V.   Conventional Commits & Structured PRs → XIV. Version Control, Review & Commits (drops `style:`, adds 50-char limit, atomic commits, branch protection)

Added principles:
  III.  Fail Gracefully and Predictably
  IV.   Bounded Retry Over REST
  V.    Scalability and Peak Load
  VI.   Security and Secrets
  VII.  Observability and Diagnosable Errors
  VIII. Versioned Contracts
  XI.   Contained Changes
  XII.  Specification Traceability
  XIII. No Silent Divergence
  XV.   Changelog Maintenance

Moved:
  - Integer PK + `uuid` model rule: from principle V → "Additional Engineering Standards".

Removed sections: none.

Templates reviewed for alignment:
  ⚠ .specify/templates/spec-template.md — does not yet open with the mandatory
     "## Inheritance from Product Spec" section (XII) nor a "Peak load" field (V).
  ⚠ .specify/templates/plan-template.md — "Constitution Check" stays generic;
     gates are derived per feature from this file. No structural change required,
     but plans MUST now check principles III, IV, V and VII explicitly.
  ✅ .specify/templates/tasks-template.md — no change required; flow tests and
     failure-path tests fit the existing testing task categories.
  ✅ .cursor/rules/specify-rules.mdc — no change; it points to the current plan.

Follow-up TODOs:
  - TODO(SPEC_TEMPLATE): add the "## Inheritance from Product Spec" block (XII)
    and a "Peak load" field (V) to .specify/templates/spec-template.md through a
    dedicated change (this skill does not modify Speckit templates).
  - TODO(CORRELATION_ID): there is no project-wide correlation/request ID
    propagated to logs and Sentry scopes (only `retail/contracts` has a
    `request_id`). Required by VII.
  - TODO(SENTRY_CONTEXT_SECRETS): `retail/clients/base.py::RequestClient` attaches
    raw request `headers` (including `Authorization`) and request/response bodies to
    log `extra` and Sentry context. Conflicts with VI/VII; must be redacted.
  - TODO(REST_RETRY_AUDIT): `RequestClient.make_request` has no retry policy and
    several services swallow propagation failures into `None`. Audit inter-service
    propagation calls against IV.
  - TODO(INLINE_LITERALS): meaningful inline literals exist (e.g.
    `timeout=43200  # 12 hours` in cache calls, `timeout=60` / `timeout=55` in
    clients). Replace with named constants when those files are touched (X, XI).
  - TODO(DEPENDENCY_SCAN): CI (`.github/workflows/ci.yaml`) has no dependency
    vulnerability check. Required by VI.
  - TODO(BRANCH_PROTECTION): confirm GitHub branch protection on `main`
    (required review + required status checks). The pre-commit
    `no-commit-to-branch` hook is local-only and does not satisfy XIV.
  - TODO(LEGACY_SPECS): specs 001–004 predate XII; they gain the inheritance
    section only when amended (see the transitional exception in XII).

Provenance:
  - Source: weni-ai/vtex-cx-engineering-constitutions (main)
  - Files: base-constitution.md, backend/base-constitution.md
  - Domains: backend
  - Project layer: previous retail-setup constitution v1.0.0, pyproject.toml,
    .github/workflows/ci.yaml, .pre-commit-config.yaml, .coveragerc,
    retail/clients/base.py, retail/observability/sentry.py, retail/settings.py
-->

# retail-setup Constitution

## Core Principles

### I. Layered Clean Architecture (NON-NEGOTIABLE)

All new code MUST respect the layered boundary `Views → Use Cases → Services → Clients`, with `Interfaces` (`typing.Protocol`, no `@runtime_checkable`) expressing client contracts.

- **Views** are thin: they validate input via a `Serializer` (in a separate `serializers.py`), build a frozen `DTO`, delegate to a Use Case, and shape the HTTP `Response`. Views MUST NOT call `Model.objects.*`, MUST NOT contain business logic, and MUST NOT import infrastructure clients directly. The view is the composition root that instantiates services and injects them into use cases.
- **Use Cases** are framework-agnostic: they hold business rules, orchestrate services, run ORM queries, and raise domain exceptions. Use Cases MUST NOT import anything from `rest_framework` and MUST NOT touch `request` objects.
- **Services** wrap clients, catch infrastructure exceptions, and log context. They MUST NOT propagate raw infrastructure errors upward; how a failure is surfaced (return `None`, domain error, or recoverable retry) MUST satisfy principles III and IV.
- **Clients** are the only layer allowed to perform outbound HTTP calls; each client implements a `Protocol` interface and is injected via `__init__` with an `Optional` fallback to the concrete implementation.

**Rationale:** Mixing layers is the most common defect class in this codebase. Locking the boundary at the constitution level gives every plan a hard, reviewable gate and keeps use cases reusable across HTTP, Celery, and EDA consumer entrypoints.

### II. Never Trust the Client

Everything that reaches the server from outside — the Weni frontend, VTEX IO apps, VTEX/Meta webhooks, EDA events, or other internal services — MUST be treated as potentially malicious, incomplete, or incorrect until validated.

- Every external input MUST be validated for type, format, range, and business rules at the server boundary before use: DRF `Serializer` for HTTP bodies/query params, explicit payload validation for webhooks and EDA consumers.
- Authorization MUST be enforced on the server for every request, regardless of checks already performed by the caller.
- Authentication and authorization MUST be expressed exclusively through DRF `permission_classes` on the view class, composed with `&` / `|` when conditions are mixed. Permission logic MUST NOT appear in view method bodies (no manual `self.check_object_permissions(...)`, no `if request.user...`), in Use Cases, or in Services. Custom permissions MUST inherit from `BasePermission`.
- When a consumer relies on a guard enforced upstream (hook filter, webhook signature, producer-side filter), that guard MUST hold on every branch of the producer, or the consumer MUST re-validate it.

**Rationale:** Callers run outside the server's control and can be inspected, modified, or bypassed. Server-side validation and declarative, centralized authorization are what prevent injection, data corruption, cross-tenant access, and silent privilege drift.

### III. Fail Gracefully and Predictably

Every external dependency (VTEX, Meta, Connect, Integrations, Flows, Crawler, S3, Redis, RabbitMQ) will eventually fail.

- Every call to an external dependency MUST have an explicit timeout and MUST NOT block indefinitely. Timeouts MUST be named constants or settings, never inline literals.
- Failures MUST be handled explicitly and surfaced as consistent, well-defined error responses (stable `detail` / `error_code` shapes), never as unhandled crashes or leaked internal details (stack traces, upstream bodies, credentials).
- Fail-safe utilities for side effects (status marking, notifications, observability enrichment) MUST NOT propagate their own exceptions.

**Rationale:** Failure is a certainty, not an edge case. Handling it explicitly keeps partial outages contained and observable instead of letting one failing dependency take the service down or expose internals to callers.

### IV. Bounded Retry Over REST

When data is propagated between services over a REST call, a failure MUST be retried rather than dropped.

- A retry MUST be attempted only for failures that could plausibly succeed on another attempt: connection error, request timeout, HTTP 5xx, or HTTP 429. A retry MUST NOT be attempted on a 4xx that reflects a defect in the request itself.
- A retry MUST only be applied to an operation that is idempotent or protected by a deduplication key; an operation that is neither MUST be made idempotent rather than left without retry.
- Every retry policy (Celery `autoretry_for` / `max_retries` / `retry_backoff`, or client-level retry) MUST define a maximum number of attempts and a backoff strategy, both as named constants or settings. Unbounded retry MUST NOT be used.
- When attempts are exhausted, the failure MUST be logged with context and MUST remain recoverable (persisted failure state, re-dispatchable task, or dead-letter queue). Returning `None` from a service MUST NOT be the only trace of a dropped propagation.

**Rationale:** Propagation between services fails for transient reasons far more often than permanent ones, so retrying keeps services converging. Retrying requests rejected on their merits, or non-idempotent operations, multiplies load or duplicates effects; bounds keep the mechanism from becoming the outage; recoverable exhaustion prevents data from disappearing between two services that each believe they succeeded.

### V. Scalability and Peak Load

- The web (gunicorn) and worker (Celery, EDA consumer) processes MUST be stateless so they scale horizontally. State that outlives a single request or task MUST NOT live in process memory or on local disk; it MUST live in a shared external store (Postgres, Redis via `django-redis`, S3). Local temporary files (e.g. generated PDFs) MUST be scoped to a single request/task.
- Distributed locks and deduplication windows MUST use the shared cache, never in-process structures.
- The peak load a feature is expected to sustain (e.g. order-status webhooks per minute during seasonal sales, broadcast fan-out) MUST be declared in its engineering spec, stated as peak and not as average.

**Rationale:** Capacity is a design input, not something discovered during an incident. Sizing for averages guarantees failure exactly when demand matters most — retail peaks such as Black Friday — and statelessness is what makes adding instances a valid answer to load.

### VI. Security and Secrets

- Secrets MUST never be committed. All configuration MUST be read via `django-environ` (`env.str()`, `env.bool()`, `env.int()`, `env.json()`); secret settings MUST default to `""`. Secrets MUST be provided by an external secrets manager and injected at runtime; local `.env` files MUST remain git-ignored.
- Access MUST follow least privilege by default (OIDC scopes, internal-communication permissions, AWS IAM).
- Dependencies MUST come only from trusted sources (PyPI via Poetry, pinned in `poetry.lock`) and MUST be checked for known vulnerabilities.
- Credentials (`Authorization` headers, tokens, client secrets, VTEX app keys) MUST NOT be written to logs, Sentry context, or error responses.

**Rationale:** Leaked credentials and untrusted dependencies are among the most common and most damaging breaches; prevention is far cheaper than remediation.

### VII. Observability and Diagnosable Errors

- Logs MUST be structured: obtained via `logging.getLogger(__name__)`, messages written as f-strings carrying identifiers as `key=value` pairs (e.g. `project_uuid=…`, `vtex_account=…`), and machine-filterable fields passed via `extra=` or Sentry tags. Level semantics: `info` for milestones, `warning` for recoverable anomalies, `error` for failures with context.
- Logs and error reports MUST NOT contain secrets or sensitive personal data — names, e-mail addresses, phone numbers, government identifiers, or message content tied to a person. Sentry MUST keep `send_default_pii=False`.
- Errors MUST be traceable across components through a correlation identifier propagated across HTTP calls, Celery tasks, and EDA events.
- Every error reported to Sentry MUST carry, at minimum, the project identifier (`project_uuid`), the account identifier (`vtex_account`), the user identifier, and the request correlation identifier, attached through `retail.observability.sentry.sentry_error_scope` tags. These identifiers MUST be opaque; a user e-mail MUST NOT be used as the user identifier in an error report.
- Sentry fingerprints MUST group by error type and tenant, never by per-request dynamic IDs.

**Rationale:** An error without identifying context can be counted but not investigated. Opaque identifiers give investigations exactly the filtering they need while keeping telemetry free of personal data, and structured fields keep incidents diagnosable without reproducing them.

### VIII. Versioned Contracts

Public interfaces — HTTP endpoints (`/api/v1`, `/api/v2`, `/api/v3`, internal endpoints), webhook receivers, EDA event payloads, and outbound payloads consumed by Flows/Connect — MUST be versioned following SemVer.

- Changes MUST be backward compatible within the same major version, or ship with an announced deprecation path and a new versioned route/payload.
- Silent breaking changes (removed/renamed fields, changed types, narrowed accepted values, changed status codes) MUST NOT be introduced.

**Rationale:** The frontend, VTEX IO apps, and sibling microservices depend on stable contracts; explicit versioning and deprecation give them a predictable path to adapt without outages.

### IX. Tests Exercise Flows & Coverage Parity (NON-NEGOTIABLE)

- Every flow MUST have at least one test covering the complete use case from input to resulting effect (e.g. `APIClient` request → view → use case → persisted state / dispatched call at the client boundary). Isolated method tests are allowed and SHOULD cover edge cases and input variations, but MUST NOT be the only coverage a flow has.
- Every flow MUST cover its success path and its failure paths; an error path that no test exercises MUST NOT be considered covered.
- Every PR MUST sustain or raise project coverage as measured by `coverage run manage.py test` and `contrib/compare_coverage.py`. Every new or modified function/branch MUST be exercised in the same PR.
- `# pragma: no cover` MUST only mark code that cannot be tested in-repo (live external providers, broker-only consumers, defensive `__main__` blocks) and MUST carry a justification. It MUST NOT be used to skip business logic.
- Tests MUST NOT reach real infrastructure: cache MUST be isolated with `@override_settings(CACHES={... LocMemCache ...})` using a unique `LOCATION` per test class; brokers, HTTP clients, S3, Connect, and Lambda MUST be mocked at the client/publisher boundary. A green local run with Redis/RabbitMQ available is not evidence of isolation.
- Integration tests SHOULD be preferred over heavy mocking when an in-process alternative exists.

**Rationale:** A suite made only of isolated method tests can be green while the composition is broken. Flow tests prove the pieces work together, failure paths are where production pain concentrates, and isolated infrastructure keeps CI deterministic.

### X. Explicit Over Clever

- What a piece of code does MUST be evident where it happens. Hidden side effects and implicit control flow MUST NOT be introduced to save lines.
- Any literal that carries meaning — a threshold, limit, TTL, timeout, retry count — MUST be a named constant or setting rather than an inline value. Literals with no meaning beyond their value (index `0`, increment `1`) are exempt.
- Names MUST carry intent. When a block needs a narrative comment to be understood, it MUST be extracted into a well-named private method (Replace Comment with Function), and a single method MUST NOT mix business flow with formatting, serialization, or logging boilerplate (SLAP).
- Comments MUST explain *why* (constraint, trade-off, external contract, ordering), never *what*. Redundant, narrative, and commented-out code MUST be removed. Code, comments, and docstrings MUST be written in English.

**Rationale:** Code is read far more often than written, usually by someone without the original context. An unexplained literal is a decision nobody can review, and comments that restate behavior silently go stale.

### XI. Contained Changes

A change MUST be limited to the context it was asked to address. Refactoring, renaming, reformatting, or behavior adjustments outside that context MUST NOT ride along; each belongs to its own change. Improvements spotted outside the scope SHOULD be reported as follow-ups. A change within scope MAY span several atomic commits (XIV).

**Rationale:** A change that reaches beyond its stated scope is a change nobody reviewed on purpose: it hides the intended fix inside unrelated edits and turns a revert into a choice between losing the fix and keeping an unrelated regression.

### XII. Specification Traceability

- Every engineering spec under `specs/<feature>/` MUST derive from exactly one approved product spec and MUST reference it through an immutable, pinned version (commit or tag); a mutable URL or ID alone MUST NOT be used.
- The product spec MUST exist and be tagged before its engineering spec is created. An engineering spec MUST NOT redefine the inherited problem, scope, success criteria, or binding decisions.
- A technical architecture document SHOULD be produced for non-trivial features; when it exists it MUST be linked and pinned by commit/tag, but its absence MUST NOT block the engineering spec.
- Every engineering spec MUST open with this section, in exactly this format:

```
## Inheritance from Product Spec
- Product Spec: <title> — <URL>
- Pinned version: <commit/tag>
- Architecture doc: <none | URL + commit/tag>
- Inherited binding decisions: <short list>
- Scope of this spec: <slice implemented by this repo>
- Divergences: <none | link to amendment>
```

- Transitional exception: specs already merged before v2.0.0 (`001`–`004`) are not retrofitted; they MUST gain the inheritance section the first time they are amended. Justification: retrofitting closed specs adds no traceability to work already shipped, while every new or changing spec is fully bound.

**Rationale:** Traceability from product intent to technical execution keeps decisions auditable. Pinning guarantees that every team implements the same version of the feature, and a single inheritance format keeps the link machine-checkable across repositories.

### XIII. No Silent Divergence

When a technical need contradicts something inherited from the product spec — scope, success criteria, or a binding decision — the divergence MUST NOT be implemented silently in code. It MUST be raised as an amendment in the product repository and recorded in the `Divergences` field, linking to that amendment. Once the amendment is approved and tagged, the engineering spec's `Pinned version` MUST be updated. A technical difference that contradicts nothing inherited is an implementation decision and MUST live in the engineering spec (`plan.md` / `research.md`).

**Rationale:** With the product spec as single source of truth, a silent code deviation lets intent and implementation drift apart with no audit trail.

### XIV. Version Control, Review & Commits

- All code MUST enter `main` through a pull request. Merge MUST require at least one approved review and a green CI run (`.github/workflows/ci.yaml`: tests, `contrib/code_check.py`, Codecov, `contrib/compare_coverage.py`). Direct pushes to `main` MUST be blocked via GitHub branch protection; the local `no-commit-to-branch` pre-commit hook is complementary, not sufficient.
- Commits MUST follow Conventional Commits: `<type>: <description>`, with type in `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. The description MUST be imperative, specific, and at most 50 characters. Commits MUST be atomic: one logical change per commit.
- Branch names MUST follow `<type>/<kebab-case-description>` using the full word (`feature/`, `fix/`, `refactor/`, `chore/`, `docs/`, `test/`).
- PR titles MUST start with a commit type prefix and MUST NOT exceed 72 characters. PR descriptions MUST contain exactly a `## What` section and a `## Why` section.

**Rationale:** The policy is only real when the platform enforces it. Conventional, atomic commits enable changelog generation and semantic versioning, and make bisecting, reverting, and reviewing cheap.

### XV. Changelog Maintenance

- Public libraries MUST maintain a changelog following Keep a Changelog, with every user-facing change under Added, Changed, Deprecated, Removed, Fixed, or Security, and version bumps following SemVer.
- `retail-setup` is a deployable service, not a public library; its `CHANGELOG.md` MUST still record every release under a SemVer heading (`# MAJOR.MINOR.PATCH`) with one Conventional Commit entry per user-facing change. Any library extracted from this repository MUST adopt Keep a Changelog.

**Rationale:** A maintained changelog communicates impact to consumers and serves as release documentation; SemVer alignment keeps upgrade expectations predictable.

## Additional Engineering Standards

- **Stack**: Python 3.10, Poetry, Django 5, Django REST Framework 3.15, `drf-yasg`, Celery + Redis (`django-redis`), Postgres via `psycopg2`, `weni-eda` for event-driven flows, `weni-commons`, `mozilla-django-oidc` for auth, Babel for i18n, `boto3` for AWS, WeasyPrint for PDFs, Sentry + Elastic APM for observability.
- **Layout**: domain apps under `retail/<domain>/` (`models.py`, `views.py`, `serializers.py`, `usecases/`, `services/`, `tests/`); API features under `retail/api/<feature>/`; outbound clients in `retail/clients/<service>/`; their protocols in `retail/interfaces/clients/<service>/`; services in `retail/services/<service>/`.
- **Models**: new models MUST use Django's integer primary key plus a public `uuid = UUIDField(default=uuid4, editable=False, unique=True)`. Legacy UUID-PK models keep their existing strategy. Timestamps MUST use `auto_now_add` / `auto_now`. Multi-field or conditional uniqueness MUST use named `UniqueConstraint`; hot-path `(project, …)` / tenant lookups MUST be indexed.
- **Dependency injection**: always through `__init__` with `Optional[Interface] = None` and a fallback to the concrete implementation.
- **Naming**: English identifiers; `PascalCase` classes with explicit suffixes (`UseCase`, `Service`, `Client`, `DTO`, `Serializer`, `Interface`, `Error`); `snake_case` functions; private helpers prefixed `_`; Celery tasks prefixed `task_`; DTOs are `@dataclass(frozen=True)`.
- **Translations / i18n**: centralized in defaults/translations modules keyed by language prefix (`pt`, `en`, `es`) with fallback to `en`. Locale files follow the VTEX Content Guide (sentence case, no trailing period on labels, gender-neutral language, glossary terms); keys are snake_case under namespaces and MUST exist in every language with identical placeholders.
- **Error handling**: Use Cases raise domain or DRF-agnostic exceptions; Services handle infrastructure errors per III/IV; Views translate domain exceptions into the stable HTTP error shape.

## Development Workflow

> New to Spec-Driven Development? Read [docs/SPEC_KIT.md](../../docs/SPEC_KIT.md) for contributor onboarding.

Every non-trivial change MUST flow through Spec-Driven Development:

1. `/speckit-constitution` — establish or amend principles (this document).
2. `/speckit-specify` — capture the *what* and *why*; open with the inheritance section (XII) and declare peak load (V).
3. `/speckit-clarify` — resolve ambiguous areas before planning.
4. `/speckit-plan` — name stack and architecture, run the Constitution Check gate (including timeouts, retry policy, statelessness, and observability context), and list `[NEEDS CLARIFICATION]` items.
5. `/speckit-tasks` — generate tasks that include flow tests, failure-path tests, and coverage tasks.
6. `/speckit-analyze` *(recommended)* — cross-artifact consistency review.
7. `/speckit-implement` — execute tasks within the scope of the spec (XI).

Quality gates that MUST pass before merging:

- `poetry run coverage run manage.py test && poetry run coverage report -m` shows no regressions on changed files (`.coveragerc` floor: `fail_under = 60`).
- `poetry run python contrib/compare_coverage.py` does not report `Number of test lines decreased`.
- `pre-commit` hooks (Black, flake8, AST/merge-conflict checks, unit tests) run clean.
- Every changed flow has a flow test covering success and failure paths (IX).
- Commits, branch, PR title, and PR description follow XIV; user-facing changes are recorded in `CHANGELOG.md` (XV).

## Governance

This constitution supersedes ad-hoc engineering practices for `retail-setup`. Its content derives from the VTEX CX engineering base constitution (root) and the backend base constitution; on conflict, the root prevails over the domain, and both prevail over project-specific adaptations. A project-level exception to a base article MUST be stated inside that article with its justification.

All PRs and reviews MUST verify compliance. Every plan's Constitution Check reads from this document; a failed gate blocks the plan from advancing to `/speckit-tasks` unless a justification is recorded in `Complexity Tracking`. `/speckit-analyze` MUST treat any conflict with a `MUST` as CRITICAL.

Amendment procedure:

1. Open a `/speckit-constitution` (or `setup-engineering` when re-syncing with the base constitutions) session describing the change.
2. Bump the version following SemVer:
   - **MAJOR** — backward-incompatible removal or redefinition of a principle.
   - **MINOR** — new principle or materially expanded guidance.
   - **PATCH** — clarifications, wording, typo fixes.
3. Update the Sync Impact Report at the top of this file, listing templates that require follow-up.
4. The constitution change MUST be committed with the `docs:` type.

**Version**: 2.0.0 | **Ratified**: 2026-05-20 | **Last Amended**: 2026-10-01
